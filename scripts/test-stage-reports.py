"""Per-stage reports: parsing, honest status, step summaries and the Nexus check."""
import hashlib
import http.server
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reports = load("reports", "render-security-reports.py")
nexus = load("nexus", "nexus-artifact-report.py")
facts = load("facts", "stage-facts.py")


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def passed(check):
    return json.dumps({"check": check, "status": "passed", "exit_code": 0,
                       "started_utc": "2026-11-05T10:00:00Z", "finished_utc": "2026-11-05T10:01:00Z"})


class RendererTests(unittest.TestCase):
    def build_fixture(self, root):
        write(root / "build/maven-result.json", passed("maven"))
        write(root / "build/maven.log", "[INFO] BUILD SUCCESS")
        write(root / "build/surefire-reports/TEST-a.xml", '<testsuite tests="3" failures="0" errors="0" skipped="1"/>')
        write(root / "build/surefire-reports/TEST-b.xml", '<testsuite tests="2" failures="1" errors="0" skipped="0"/>')
        write(root / "build/jacoco/jacoco.xml",
              '<?xml version="1.0"?><!DOCTYPE report PUBLIC "-//JACOCO//DTD Report 1.1//EN" "report.dtd">'
              '<report name="x"><counter type="LINE" missed="25" covered="75"/><counter type="CLASS" missed="0" covered="9"/></report>')
        write(root / "quality/sonar-result.json", passed("sonar"))
        write(root / "quality/sonar.log", "[INFO] QUALITY GATE STATUS: PASSED - View details on https://sonar.example.test/dashboard?id=student-management")
        write(root / "quality/report-task.txt", "projectKey=student-management\ndashboardUrl=https://sonar.example.test/dashboard?id=student-management\n")
        write(root / "artifact/nexus-artifact-facts.json", json.dumps({"stage": "nexus-artifact", "facts": {
            "match": "true", "snapshot_version": "0.0.1-20261105.100000-1",
            "repository_url": "https://nexus.example.test:8443/repository/maven-snapshots/tn/esprit/student-management/0.0.1-SNAPSHOT/"}}))
        write(root / "image/trivy-image.json", json.dumps({"ArtifactName": "student-management:abc", "Results": [
            {"Target": "alpine", "Vulnerabilities": [{"Severity": "HIGH"}, {"Severity": "LOW"}]},
            {"Target": "app.jar", "Vulnerabilities": [{"Severity": "CRITICAL"}]}, {"Target": "empty"}]}))

    def test_build_quality_artifact_and_image_are_measured_and_linked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_fixture(root)
            reports.render(root)
            text = (root / "index.html").read_text(encoding="utf-8")
            self.assertIn("Surefire: 5 tests in 2 classes, 1 failures, 0 errors, 1 skipped", text)
            self.assertIn("JaCoCo line coverage: 75.0% (75/100)", text)
            self.assertIn("SonarQube quality gate: PASSED", text)
            self.assertIn("https://sonar.example.test/dashboard?id=student-management", text)
            self.assertIn("https://nexus.example.test:8443/#browse/browse:maven-snapshots", text)
            self.assertIn("1 CRITICAL, 1 HIGH findings across 3 scanned targets", text)
            for stage in ("build", "quality", "artifact", "image"):
                self.assertTrue((root / stage / "report.html").is_file(), stage)

    def test_unrun_stages_are_never_reported_as_passed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_fixture(root)
            reports.render(root)
            self.assertEqual(reports.stage_status(root, "build"), "passed")
            for stage in ("registry", "deploy", "monitoring", "acceptance", "sast"):
                self.assertEqual(reports.stage_status(root, stage), "not run in this snapshot", stage)

    def test_stage_without_evidence_has_no_invented_measurement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_fixture(root)
            reports.render(root)
            text = (root / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("full available Git history", text)  # secrets stage never ran here
            self.assertNotIn("hook transcript and threat model", text)
            self.assertNotIn("not available packages analyzed", text)

    def test_failed_stage_stays_failed_when_others_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.build_fixture(root)
            write(root / "image/trivy-image-result.json", json.dumps({"check": "trivy-image", "status": "failed", "exit_code": 1,
                                                                      "started_utc": "a", "finished_utc": "b"}))
            reports.render(root)
            self.assertEqual(reports.stage_status(root, "image"), "failed")
            self.assertEqual(reports.stage_status(root, "build"), "passed")
            self.assertIn("class='failed'>failed", (root / "index.html").read_text(encoding="utf-8"))

    def test_entity_declarations_in_build_xml_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TEST-x.xml"
            path.write_text('<!DOCTYPE a [<!ENTITY e "x">]><testsuite tests="1"/>')
            with self.assertRaises(ValueError):
                reports.parse_xml(path)


class StepSummaryTests(unittest.TestCase):
    def test_capture_and_facts_write_to_the_job_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / "summary.md"
            env = dict(os.environ, GITHUB_STEP_SUMMARY=str(summary))
            subprocess.run([sys.executable, str(ROOT / "scripts/capture-check.py"), "tool", directory, "--",
                            sys.executable, "-c", "print('ok')"], env=env, check=True, capture_output=True)
            subprocess.run([sys.executable, str(ROOT / "scripts/stage-facts.py"), directory, "tool",
                            "digest=sha256:abc"], env=env, check=True, capture_output=True)
            text = summary.read_text(encoding="utf-8")
            self.assertIn("**tool**: passed (exit 0)", text)
            self.assertIn("digest=`sha256:abc`", text)
            self.assertEqual(json.loads((Path(directory) / "tool-facts.json").read_text())["facts"]["digest"], "sha256:abc")

    def test_facts_reject_unsafe_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                facts.record(directory, "tool", ["bad key=1"])


METADATA = """<metadata><groupId>tn.esprit</groupId><artifactId>student-management</artifactId><version>0.0.1-SNAPSHOT</version>
<versioning><lastUpdated>20261105100000</lastUpdated><snapshotVersions>
<snapshotVersion><extension>jar</extension><value>0.0.1-20261105.090000-1</value><updated>20261105090000</updated></snapshotVersion>
<snapshotVersion><extension>jar</extension><value>0.0.1-20261105.100000-2</value><updated>20261105100000</updated></snapshotVersion>
<snapshotVersion><extension>pom</extension><value>0.0.1-20261105.100000-2</value><updated>20261105100000</updated></snapshotVersion>
</snapshotVersions></versioning></metadata>"""
POM = """<project xmlns="http://maven.apache.org/POM/4.0.0"><groupId>tn.esprit</groupId><artifactId>student-management</artifactId><version>0.0.1-SNAPSHOT</version></project>"""


class FakeNexus(http.server.BaseHTTPRequestHandler):
    sha1 = ""
    metadata = METADATA
    seen_auth = []

    def do_GET(self):
        FakeNexus.seen_auth.append(self.headers.get("Authorization"))
        base = "/tn/esprit/student-management/0.0.1-SNAPSHOT/"
        routes = {base + "maven-metadata.xml": FakeNexus.metadata.encode(),
                  base + "student-management-0.0.1-20261105.100000-2.jar.sha1": FakeNexus.sha1.encode() + b"  student-management.jar\n"}
        if self.path in routes:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(routes[self.path])
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


class NexusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), FakeNexus)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.jar = self.root / "app.jar"
        self.jar.write_bytes(b"tested jar bytes")
        self.pom = self.root / "pom.xml"
        self.pom.write_text(POM)
        FakeNexus.metadata = METADATA
        FakeNexus.seen_auth.clear()

    def tearDown(self):
        self.directory.cleanup()

    def verify(self):
        return nexus.verify(self.url, self.jar, self.pom, "ci", "secret-value", attempts=1, require_https=False)

    def test_matching_jar_is_verified_using_the_newest_snapshot(self):
        FakeNexus.sha1 = hashlib.sha1(b"tested jar bytes").hexdigest()
        result = self.verify()
        self.assertEqual(result["match"], "true")
        self.assertEqual(result["snapshot_version"], "0.0.1-20261105.100000-2")
        self.assertTrue(all(value and value.startswith("Basic ") for value in FakeNexus.seen_auth))

    def test_different_stored_jar_is_reported_as_a_mismatch(self):
        FakeNexus.sha1 = hashlib.sha1(b"some other jar").hexdigest()
        self.assertEqual(self.verify()["match"], "false")

    def test_missing_repository_entry_fails_instead_of_passing(self):
        FakeNexus.metadata = "<metadata><versioning/></metadata>"
        with self.assertRaises(RuntimeError):
            self.verify()

    def test_dtd_in_repository_metadata_is_rejected(self):
        FakeNexus.metadata = '<!DOCTYPE m [<!ENTITY e "x">]><metadata/>'
        with self.assertRaises(RuntimeError):
            self.verify()

    def test_plain_http_is_refused_in_production_mode(self):
        with self.assertRaises(ValueError):
            nexus.verify("http://nexus.example.test/", self.jar, self.pom, "ci", "x")

    def test_local_http_exception_applies_only_to_this_machine(self):
        FakeNexus.sha1 = hashlib.sha1(b"tested jar bytes").hexdigest()
        env = dict(os.environ, NEXUS_USERNAME="ci", NEXUS_PASSWORD="secret-value")
        script = str(ROOT / "scripts/nexus-artifact-report.py")
        ok = subprocess.run([sys.executable, script, "--allow-local-http", self.url, str(self.jar), str(self.pom), str(self.root / "out")],
                            env=env, capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.assertNotIn("secret-value", ok.stdout + ok.stderr)
        remote = subprocess.run([sys.executable, script, "--allow-local-http", "http://nexus.example.test/", str(self.jar), str(self.pom),
                                 str(self.root / "out2")], env=env, capture_output=True, text=True)
        self.assertNotEqual(remote.returncode, 0)


notify = load("notify", "notify-pipeline.py")


class EmailNotificationTests(unittest.TestCase):
    ENV = {"SMTP_HOST": "smtp.example.test", "SMTP_USERNAME": "u", "SMTP_PASSWORD": "never-shown", "MAIL_FROM": "a@example.test",
           "MAIL_TO": "b@example.test", "RUN_URL": "https://github.com/o/r/actions/runs/1", "RUN_RESULT": "failure",
           "WORKFLOW_NAME": "Coursework pipeline",
           "JOB_RESULTS": json.dumps({"security": {"result": "success", "outputs": {}},
                                      "delivery": {"result": "failure", "outputs": {"image": "registry.example/app@sha256:" + "a" * 64}}})}

    def test_message_lists_every_stage_result_and_the_run_link(self):
        message = notify.build_message(self.ENV)
        body = message.get_content()
        self.assertEqual(message["Subject"], "DevSecOps Coursework pipeline: failure")
        self.assertIn("security: success", body)
        self.assertIn("delivery: failure", body)
        self.assertIn(self.ENV["RUN_URL"], body)

    def test_message_never_contains_credentials_or_job_outputs(self):
        body = notify.build_message(self.ENV).get_content()
        self.assertNotIn("never-shown", body)
        self.assertNotIn("sha256:", body)

    def test_missing_configuration_fails_instead_of_sending(self):
        with self.assertRaises(SystemExit):
            notify.build_message({k: v for k, v in self.ENV.items() if k != "SMTP_HOST"})


class EmailIsTheLastStageTests(unittest.TestCase):
    def test_every_pipeline_workflow_ends_with_an_always_email_job(self):
        import yaml
        for name in ("coursework", "devsecops", "acceptance-nmap", "pipeline"):
            workflow = yaml.safe_load((ROOT / f".github/workflows/{name}.yml").read_text(encoding="utf-8"))
            jobs = workflow["jobs"]
            self.assertIn("email", jobs, name)
            email = jobs["email"]
            others = set(jobs) - {"email"}
            self.assertEqual(others, set(email["needs"]) if isinstance(email["needs"], list) else {email["needs"]},
                             f"{name}: email must wait for every other job")
            self.assertTrue(email["if"].startswith("always()"), name)
            self.assertIn("EMAIL_ENABLED", email["if"], name)
            self.assertEqual(email["environment"], "azure-lab", name)
            self.assertIn("JOB_RESULTS", email["steps"][-1]["env"], name)

    def test_dependabot_is_a_reported_production_phase_in_both_pipelines(self):
        import yaml
        for name, after in (("coursework", "acceptance"), ("devsecops", "trivy"), ("pipeline", "pipeline")):
            jobs = yaml.safe_load((ROOT / f".github/workflows/{name}.yml").read_text(encoding="utf-8"))["jobs"]
            job = jobs["dependabot"]
            self.assertEqual(job["needs"], after, name)
            self.assertEqual(job["permissions"].get("vulnerability-alerts"), "read", name)
            self.assertEqual(job["permissions"].get("contents"), "read", name)
            self.assertNotIn("write", job["permissions"].values(), name)
            self.assertIn("dependabot", jobs["reports"]["needs"], name)
            self.assertIn("dependabot-report.py", job["steps"][-2]["run"], name)
            self.assertEqual(job["steps"][-1]["with"]["name"], "stage-dependabot", name)


dependabot = load("dependabot", "dependabot-report.py")


class FakeGitHub(http.server.BaseHTTPRequestHandler):
    alerts_mode = "disabled"
    pulls_status = 200

    def reply(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/repos/o/r/pulls":
            if FakeGitHub.pulls_status != 200:
                return self.reply(FakeGitHub.pulls_status, {"message": "Resource not accessible by integration"})
            self.reply(200, [
                {"number": 7, "title": "chore(deps): bump maven from 3.9.11-eclipse-temurin-17 to 3.9-eclipse-temurin-26",
                 "head": {"ref": "dependabot/docker/maven-3.9-eclipse-temurin-26", "sha": "a1"}, "user": {"login": "dependabot[bot]"},
                 "created_at": "2026-11-01T00:00:00Z", "html_url": "https://github.com/o/r/pull/7"},
                {"number": 9, "title": "Bump actions/checkout from 4.4.0 to 7.0.1",
                 "head": {"ref": "dependabot/github_actions/actions/checkout-7.0.1", "sha": "b2"}, "user": {"login": "dependabot[bot]"},
                 "created_at": "2026-11-10T00:00:00Z", "html_url": "https://github.com/o/r/pull/9"},
                {"number": 30, "title": "Human change", "head": {"ref": "feature", "sha": "c3"}, "user": {"login": "oussamakou"},
                 "created_at": "2026-11-10T00:00:00Z", "html_url": "https://github.com/o/r/pull/30"}])
        elif path == "/repos/o/r/commits/a1/check-runs":
            self.reply(200, {"check_runs": [{"status": "completed", "conclusion": "success"}, {"status": "completed", "conclusion": "failure"}]})
        elif path == "/repos/o/r/commits/b2/check-runs":
            self.reply(200, {"check_runs": [{"status": "completed", "conclusion": "success"}, {"status": "completed", "conclusion": "skipped"}]})
        elif path == "/repos/o/r/dependabot/alerts":
            if FakeGitHub.alerts_mode == "disabled":
                self.reply(403, {"message": "Dependabot alerts are disabled for this repository."})
            else:
                self.reply(200, [{"number": 1, "created_at": "2026-11-09T00:00:00Z", "html_url": "https://github.com/o/r/security/dependabot/1",
                                  "dependency": {"package": {"ecosystem": "maven", "name": "com.fasterxml.jackson.core:jackson-databind"},
                                                 "manifest_path": "pom.xml", "relationship": "transitive"},
                                  "security_advisory": {"ghsa_id": "GHSA-xxxx-yyyy-zzzz", "cve_id": "CVE-2026-0001", "summary": "Fixture advisory"},
                                  "security_vulnerability": {"severity": "high", "vulnerable_version_range": "< 2.21.7",
                                                             "first_patched_version": {"identifier": "2.21.7"}}}])
        else:
            self.reply(404, {"message": "Not Found"})

    def log_message(self, *args):
        pass


class DependabotReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), FakeGitHub)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        FakeGitHub.alerts_mode, FakeGitHub.pulls_status = "disabled", 200

    def collect(self):
        from datetime import datetime, timezone
        return dependabot.collect("o/r", "token-value", self.base, ROOT / ".github/dependabot.yml",
                                  now=datetime(2026, 11, 11, tzinfo=timezone.utc))

    def test_update_types_including_docker_variant_changes(self):
        cases = {("Bump a from 4.4.0 to 7.0.1", "major"), ("Bump a from 3.9.11 to 3.10.0", "minor"),
                 ("Bump a from 0.8.11 to 0.8.15", "patch"), ("Bump a from 17-jre-alpine to 25-jre-alpine", "major"),
                 ("Bump a from 3.9.11-eclipse-temurin-17 to 3.9-eclipse-temurin-26", "variant"), ("Bump a from latest to stable", "unknown")}
        for title, kind in cases:
            self.assertEqual(dependabot.parse_update(title, "dependabot/docker/x")["update_type"], kind, title)
        self.assertEqual(dependabot.parse_update("Bump a from 1 to 2", "dependabot/github_actions/x")["ecosystem"], "github-actions")

    def test_ci_state(self):
        self.assertEqual(dependabot.ci_state([]), "no checks")
        self.assertEqual(dependabot.ci_state([{"status": "in_progress"}]), "pending")
        self.assertEqual(dependabot.ci_state([{"status": "completed", "conclusion": "timed_out"}]), "failing")
        self.assertEqual(dependabot.ci_state([{"status": "completed", "conclusion": "neutral"}]), "passing")

    def test_disabled_alerts_are_a_finding_not_zero_alerts(self):
        evidence = self.collect()
        self.assertEqual([u["number"] for u in evidence["update_pull_requests"]], [7, 9])  # human PR excluded
        self.assertEqual(evidence["update_pull_requests"][0]["ci"], "failing")
        self.assertEqual(evidence["update_pull_requests"][0]["age_days"], 10)
        self.assertEqual(evidence["alerts"]["status"], "disabled")
        unmet = {c["name"] for c in evidence["checks"] if c["required"] and not c["ok"]}
        self.assertEqual(unmet, {"Dependabot security alerts enabled and readable", "No open HIGH/CRITICAL Dependabot alerts"})
        self.assertIn("security alerts DISABLED", evidence["summary"])
        self.assertNotIn("token-value", json.dumps(evidence))

    def test_high_alert_is_reported_with_its_fix(self):
        FakeGitHub.alerts_mode = "enabled"
        evidence = self.collect()
        alert = evidence["alerts"]["open"][0]
        self.assertEqual((alert["severity"], alert["patched"], alert["ghsa"]), ("high", "2.21.7", "GHSA-xxxx-yyyy-zzzz"))
        failed = {c["name"] for c in evidence["checks"] if c["required"] and not c["ok"]}
        self.assertEqual(failed, {"No open HIGH/CRITICAL Dependabot alerts"})

    def test_unreadable_pull_requests_fail_the_collection(self):
        FakeGitHub.pulls_status = 403
        with self.assertRaises(RuntimeError):
            self.collect()

    def test_report_highlights_dependabot_findings_without_failing_the_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "dependabot").mkdir()
            (root / "dependabot/dependabot-evidence.json").write_text(json.dumps(self.collect()))
            reports.render(root)
            self.assertEqual(reports.stage_status(root, "dependabot"), "attention")
            page = (root / "dependabot/report.html").read_text(encoding="utf-8")
            self.assertIn("class='banner'", page)
            self.assertIn("variant", page)
            self.assertIn("class=failed>failing", page)
            self.assertIn("class='attention'>attention", (root / "index.html").read_text(encoding="utf-8"))


nmap = load("nmap_acceptance", "nmap-acceptance.py")
deploy_runner = load("deploy_runner", "deploy-on-runner.py")


class RunnerLaneTests(unittest.TestCase):
    def workflow(self, name):
        import yaml
        return yaml.safe_load((ROOT / f".github/workflows/{name}.yml").read_text(encoding="utf-8"))

    def test_runner_lane_runs_every_stage_in_order_and_azure_lane_is_manual(self):
        pipeline = self.workflow("pipeline")
        triggers = pipeline[True] if True in pipeline else pipeline["on"]  # PyYAML reads the key `on` as True
        self.assertEqual(set(triggers), {"push", "pull_request", "workflow_dispatch"})
        self.assertEqual(pipeline["jobs"]["pipeline"]["needs"], "security")
        numbered = [s["name"] for s in pipeline["jobs"]["pipeline"]["steps"] if s.get("name", "")[:1].isdigit()]
        self.assertEqual([int(n.split(" ")[0]) for n in numbered], list(range(1, 10)))
        coursework = self.workflow("coursework")
        self.assertEqual(set(coursework[True] if True in coursework else coursework["on"]), {"workflow_dispatch"})

    def test_runner_policy_scans_only_this_runner(self):
        policy = nmap.load_policy(ROOT / "security/nmap-policy-runner.json")
        self.assertNotIn("private_scanner_hostname", policy)
        self.assertEqual(policy["profiles"]["public"][0]["target"], "self")
        loopback = policy["profiles"]["private"][0]
        self.assertEqual((loopback["target"], loopback["allowed_open"]), ("127.0.0.1", [3000, 5000, 8089, 9091]))
        self.assertNotIn(3306, loopback["allowed_open"])
        from unittest import mock
        with mock.patch.object(nmap, "primary_ipv4", return_value="10.1.0.4"):
            self.assertEqual(nmap.resolve(policy["profiles"]["public"][0])["target"], "10.1.0.4")

    def test_policy_without_pinned_scanner_may_not_scan_other_hosts_privately(self):
        with tempfile.TemporaryDirectory() as directory:
            data = json.loads((ROOT / "security/nmap-policy-runner.json").read_text(encoding="utf-8"))
            data["profiles"]["private"][0]["target"] = "10.42.1.4"
            path = Path(directory) / "policy.json"
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                nmap.load_policy(path)

    def test_azure_policy_is_unchanged_and_still_pins_its_scanner(self):
        policy = nmap.load_policy(ROOT / "security/nmap-policy.json")
        self.assertEqual(policy["private_scanner_hostname"], "studentcourse-vm")

    def test_screenshots_refuse_anything_but_the_runner_itself(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/capture-ui-screenshots.py"), tempfile.gettempdir(), "x",
                                 "evil=https://example.com/"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be 127.0.0.1", result.stdout + result.stderr)

    def test_runner_deployment_uses_the_lab_compose_and_private_passwords(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(deploy_runner, "RUNTIME", Path(directory) / "runtime"):
                image = "localhost:5000/student-management@sha256:" + "b" * 64
                deploy_runner.assemble(image)
                runtime = Path(directory) / "runtime"
                self.assertEqual((runtime / "compose.yml").read_text(encoding="utf-8"),
                                 (ROOT / "cloud/runtime/compose.yml").read_text(encoding="utf-8"))
                for name in ("prometheus.yml", "datasources.yml", "dashboards.yml", "vms.json", "student.json", "runner-overrides.yml"):
                    self.assertTrue((runtime / name).is_file(), name)
                env = (runtime / ".env").read_text(encoding="utf-8")
                self.assertIn(f"APP_IMAGE={image}", env)
                self.assertEqual(len([line for line in env.splitlines() if re.fullmatch(r"\w+_PASSWORD=[0-9a-f]{64}", line)]), 3)
                self.assertIn("GF_AUTH_ANONYMOUS_ORG_ROLE: Viewer", (runtime / "runner-overrides.yml").read_text(encoding="utf-8"))
        self.assertFalse(deploy_runner.IMAGE.fullmatch("evil.example/student-management@sha256:" + "b" * 64))


final_report = load("final_report", "build-final-report.py")


class FinalReportTests(unittest.TestCase):
    def test_every_cited_screenshot_exists(self):
        missing = [n for n in final_report.referenced_files() if not (final_report.SHOTS / n).is_file()]
        self.assertEqual(missing, [])

    def test_statuses_are_valid_and_unproven_stages_have_no_fake_proof(self):
        stages = [s for phase in final_report.CATALOG for s in phase["stages"]]
        for stage in stages:
            self.assertIn(stage["status"], final_report.STATUSES, stage["id"])
        pending = [s for s in stages if s["status"] == "pending"]
        self.assertTrue(all(not s["proof"] for s in pending), "a pending stage must not cite a screenshot")
        self.assertTrue(all(s["proof"] for s in stages if s["status"] == "verified"), "a verified stage must cite proof")

    def test_every_report_page_the_renderer_creates_is_listed(self):
        listed = " ".join(s["report"] for phase in final_report.CATALOG for s in phase["stages"])
        for folder, _, _ in reports.STAGES:
            if folder in ("precommit", "sast", "secrets", "dependencies", "iac", "acceptance", "monitoring", "prometheus", "grafana", "dependabot"):
                self.assertIn(folder + "/", listed, folder)
        for folder in ("build", "quality", "artifact", "image", "registry", "deploy"):
            self.assertIn(folder + "/report.html", listed, folder)

    def test_report_states_what_is_still_unproven(self):
        text = final_report.build("test")
        self.assertIn("Not yet proven", text)
        self.assertTrue(final_report.PENDING_PROOF)
        labels = {"verified": "Verified in a real run", "partial": "Partly verified", "pending": "Implemented, not yet run live"}
        for status in {s["status"] for phase in final_report.CATALOG for s in phase["stages"]}:
            self.assertIn(labels[status], text, status)
        self.assertIn("data:image/png;base64,", text)


guest = load("guest", "monitoring-vm-evidence.py")
runner = load("azmon", "azure-monitoring-evidence.py")


class FakeMonitoring(http.server.BaseHTTPRequestHandler):
    grafana_auth = []
    dashboards = [{"title": "Student API", "uid": "student-devsecops", "url": "/d/student-devsecops/student-api"},
                  {"title": "Azure VMs", "uid": "student-vms", "url": "/d/student-vms/azure-vms"}]
    app_target_health = "up"

    def reply(self, body):
        data = json.dumps(body).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path == "/api/v1/targets":
            self.reply({"data": {"activeTargets": [
                {"labels": {"job": "student-api", "instance": "app:9090"}, "health": FakeMonitoring.app_target_health,
                 "lastScrape": "2026-11-05T12:00:00Z", "scrapeUrl": "http://app:9090/actuator/prometheus", "lastError": ""},
                {"labels": {"job": "azure-nodes", "instance": "10.42.1.4:9100", "host": "application-vm"}, "health": "up", "lastScrape": "x"},
                {"labels": {"job": "azure-nodes", "instance": "10.42.2.4:9100", "host": "tools-vm"}, "health": "up", "lastScrape": "x"}]}})
        elif path == "/api/v1/query":
            nan = "histogram_quantile" in query
            self.reply({"data": {"result": [{"metric": {}, "value": [1, "NaN" if nan else "2.5"]}]}})
        elif path == "/api/v1/query_range":
            self.reply({"data": {"result": [{"metric": {"host": "tools-vm"}, "values": [[1, "1.0"], [31, "3.5"], [61, "2.0"]]}]}})
        elif path == "/api/v1/rules":
            self.reply({"data": {"groups": []}})
        elif path == "/api/health":
            self.reply({"database": "ok", "version": "13.2.4"})
        elif path == "/api/datasources":
            FakeMonitoring.grafana_auth.append(self.headers.get("Authorization"))
            self.reply([{"name": "Prometheus", "type": "prometheus", "url": "http://prometheus:9090", "isDefault": True}])
        elif path == "/api/search":
            self.reply(FakeMonitoring.dashboards)
        elif path == "/student/students/getAllStudents":
            self.reply([])
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


class MonitoringEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), FakeMonitoring)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root / ".env").write_text("MYSQL_ROOT_PASSWORD=x\nGRAFANA_PASSWORD=very-secret-grafana-value\n")
        FakeMonitoring.app_target_health = "up"
        FakeMonitoring.grafana_auth.clear()

    def tearDown(self):
        self.directory.cleanup()

    def sample(self):
        return guest.collect(self.url, self.url, self.url + "/student/students/getAllStudents", self.root / ".env",
                             traffic=3, pause=0, settle=0)

    def test_collects_targets_dashboards_and_never_stores_the_grafana_password(self):
        evidence = self.sample()
        self.assertTrue(all(c["ok"] for c in evidence["checks"]), evidence["checks"])
        self.assertEqual(evidence["traffic"], {"endpoint": "GET /student/students/getAllStudents (read-only)", "requests": 3, "succeeded": 3})
        self.assertEqual({d["uid"] for d in evidence["grafana"]["dashboards"]}, {"student-devsecops", "student-vms"})
        self.assertIsNone(evidence["prometheus"]["instant"]["95th percentile latency (s)"]["result"][0]["value"])  # NaN is not a zero
        self.assertNotIn("very-secret-grafana-value", json.dumps(evidence))
        self.assertTrue(FakeMonitoring.grafana_auth and all(a.startswith("Basic ") for a in FakeMonitoring.grafana_auth))

    def test_down_target_and_missing_dashboard_fail_required_checks(self):
        FakeMonitoring.app_target_health = "down"
        saved = FakeMonitoring.dashboards
        FakeMonitoring.dashboards = saved[:1]
        try:
            names = {c["name"] for c in self.sample()["checks"] if c["required"] and not c["ok"]}
        finally:
            FakeMonitoring.dashboards = saved
        self.assertEqual(names, {"Prometheus student-api target UP", "Grafana dashboards provisioned"})

    def test_evidence_survives_chunked_transport_and_tampering_is_detected(self):
        import base64
        import io
        import zipfile
        evidence = self.sample()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("evidence.json", json.dumps(evidence))
        payload = buffer.getvalue()
        encoded = base64.b64encode(payload).decode()
        pieces = [encoded[i:i + 400] for i in range(0, len(encoded), 400)]
        digest = hashlib.sha256(payload).hexdigest()
        manifest = lambda i: {"id": "a" * 32, "index": i, "chunks": len(pieces), "sha256": digest, "payload": pieces[i]}  # noqa: E731
        data, _, count, _ = runner.reassemble(manifest(0), lambda ident, i: manifest(i))
        self.assertGreater(count, 1)
        self.assertEqual(runner.unpack(data)["checks"], evidence["checks"])
        tampered = lambda ident, i: dict(manifest(i), payload=pieces[i][::-1]) if i == 1 else manifest(i)  # noqa: E731
        with self.assertRaises(ValueError):
            runner.reassemble(manifest(0), tampered)
        wrong = lambda ident, i: dict(manifest(i), id="b" * 32)  # noqa: E731
        with self.assertRaises(ValueError):
            runner.reassemble(manifest(0), wrong)

    def test_unexpected_archive_contents_are_rejected(self):
        import io
        import zipfile
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("../evil.json", "{}")
        with self.assertRaises(ValueError):
            runner.unpack(buffer.getvalue())

    def test_reports_render_prometheus_and_grafana_pages_and_failures_stay_failed(self):
        evidence = self.sample()
        failed = runner.write_reports(evidence, self.root / "reports")
        self.assertEqual(failed, [])
        reports.render(self.root / "reports")
        page = (self.root / "reports/grafana/report.html").read_text(encoding="utf-8")
        self.assertIn("<svg", page)
        self.assertIn("not</strong> a Grafana screenshot", page)
        self.assertIn("http://127.0.0.1:3000/d/student-devsecops/student-api", page)
        prometheus_page = (self.root / "reports/prometheus/report.html").read_text(encoding="utf-8")
        self.assertIn("10.42.2.4:9100", prometheus_page)
        index = (self.root / "reports/index.html").read_text(encoding="utf-8")
        self.assertIn("3 of 3 scrape targets UP", index)
        evidence["checks"][0]["ok"] = False
        self.assertEqual(len(runner.write_reports(evidence, self.root / "reports")), 1)
        self.assertEqual(reports.stage_status(self.root / "reports", "prometheus"), "failed")
        self.assertEqual(reports.stage_status(self.root / "reports", "grafana"), "passed")


if __name__ == "__main__":
    unittest.main()
