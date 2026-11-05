"""Per-stage reports: parsing, honest status, step summaries and the Nexus check."""
import hashlib
import http.server
import importlib.util
import json
import os
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
