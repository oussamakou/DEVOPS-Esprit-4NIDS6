"""Build the final report: every stage, technique, tool, its report and screenshot proof.

Writes a self-contained HTML file (screenshots embedded) and, with --pdf, a PDF
printed by Chrome. The catalog below is the single list of what the pipeline
does; test-stage-reports.py checks that every screenshot it cites exists and
that every report page the renderer produces is listed.

Usage: python scripts/build-final-report.py [--pdf] [--chrome PATH]
       [--tool-reports ARCHIVE] [--append-pdf PDF ...]
"""
import argparse
import base64
import html
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from datetime import date
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "documentation/screenshots"
REPO = "https://github.com/oussamakou/DEVOPS-Esprit-4NIDS6"
RUN = REPO + "/actions/runs/"
HOSTED_RUN = "43076300738"
HOSTED_ARTIFACT = f"{RUN}{HOSTED_RUN}/artifacts/13881273531"
HOSTED_SHOT = f"hosted_run{HOSTED_RUN}_"
AZURE_RUN = "42108525318"
EVIDENCE_RUN = "43082725820"
EVIDENCE_ARTIFACT = f"{RUN}{EVIDENCE_RUN}/artifacts/13885372898"
TOOL_REPORTS = (
    ("precommit", "Pre-commit and threat model"), ("sast", "Semgrep SAST"),
    ("secrets", "Gitleaks"), ("dependencies", "Trivy dependencies and SBOM"),
    ("iac", "Terraform and Checkov"), ("build", "Maven, Surefire and JaCoCo"),
    ("quality", "SonarQube"), ("artifact", "Nexus"), ("image", "Docker and Trivy image scan"),
    ("registry", "Registry and digest"), ("deploy", "Compose acceptance lab"),
    ("acceptance", "Nmap"), ("production", "Production smoke test"),
    ("monitoring", "Operations verification"), ("prometheus", "Prometheus and Node Exporter"),
    ("grafana", "Grafana"), ("dependabot", "Dependabot"),
)

# status: verified = a real run produced it; partial = part verified; pending = implemented, not yet seen live.
STATUSES = {"verified", "partial", "pending"}

# (file, caption). Captions state what the image shows and which run it comes from.
CATALOG = [
    {"phase": "A. Development", "stages": [
        {"id": "threat", "name": "Threat modelling", "technique": "STRIDE threat model, reviewed by a human before coding",
         "tool": "documentation/THREAT-MODEL.md", "gate": "The document must exist; CI preserves it with the run's reports", "report": "precommit/THREAT-MODEL.md",
         "status": "verified", "note": "Threat modelling is a human review: a green job proves the file is preserved, not that the analysis is complete.",
         "proof": [("report_precommit_hooks_run40899036172.png", "Pre-commit report page that preserves the threat model (run 40899036172, 29 Oct 2026)")]},
        {"id": "precommit", "name": "Pre-commit hooks", "technique": "Local hooks replayed in CI: YAML/XML validity, merge markers, private-key headers, staged-secret scan",
         "tool": "pre-commit, Gitleaks (staged snapshot)", "gate": "Any hook failure stops the pipeline", "report": "precommit/report.html",
         "status": "verified", "note": "", "proof": [("report_precommit_hooks_run40899036172.png", "Hook transcript with Passed results (run 40899036172)")]},
        {"id": "sast", "name": "Static application security testing", "technique": "SAST with project rules for command execution, concatenated SQL and disabled TLS verification",
         "tool": "Semgrep", "gate": "Any finding fails (--error --strict)", "report": "sast/report.html",
         "status": "verified", "note": "Deliberately narrow rule set, complemented by SonarQube.",
         "proof": [("report_semgrep_sast_run40899036172.png", "19 files scanned, 3 rules, 0 findings (run 40899036172)")]},
        {"id": "secrets", "name": "Secret scanning", "technique": "Full Git history scan with redacted output",
         "tool": "Gitleaks", "gate": "Any new finding fails; one exact historical fingerprint is documented in SECURITY.md", "report": "secrets/report.html",
         "status": "verified", "note": "", "proof": [("report_gitleaks_secrets_run40899036172.png", "Gitleaks history scan passed (run 40899036172)")]},
        {"id": "dependencies", "name": "Dependency analysis and SBOM", "technique": "Software composition analysis of the source POM with a CycloneDX inventory",
         "tool": "Trivy", "gate": "HIGH/CRITICAL fails; empty or unversioned inventory is rejected", "report": "dependencies/report.html",
         "status": "verified", "note": "An earlier green run had an empty inventory; the validator now rejects that.",
         "proof": [("report_trivy_dependencies_run40899036172.png", "Verified inventory and SBOM summary (run 40899036172)")]},
        {"id": "iac", "name": "Infrastructure-as-code policy", "technique": "Terraform fmt/validate, policy scan, custom SSH-to-internet rule, workflow lint, Caddy config validation",
         "tool": "Terraform, Checkov, actionlint", "gate": "Any unexcepted failure; ten exclusions are documented in SECURITY.md", "report": "iac/report.html",
         "status": "verified", "note": "",
         "proof": [("report_checkov_iac_run40899036172.png", "Checkov policy counts (run 40899036172)"),
                   ("coursework_checkov_failed.png", "Real finding CKV_AZURE_160 (public HTTP port 80) failing the gate (run 39805052147)"),
                   ("coursework_checkov_passed.png", "Passing rescan after the port was closed (run 39805591559)")]},
        {"id": "collect", "name": "Collect pre-build reports", "technique": "Aggregate every scanner output into one readable index",
         "tool": "scripts/render-security-reports.py", "gate": "Runs even after a failed gate", "report": "index.html",
         "status": "verified", "note": "", "proof": [("report_index_all_stages_run42055245961.png", "Combined index generated by CI (run 42055245961, pull request 25)")]},
    ]},
    {"phase": "B. Acceptance", "stages": [
        {"id": "maven", "name": "Compile, test and coverage", "technique": "Unit and HTTP integration tests with coverage measurement",
         "tool": "Maven, JUnit (Surefire), JaCoCo", "gate": "Any failed test blocks the image build", "report": "build/report.html",
         "status": "verified", "note": "6 tests, 41.5% line coverage in the CI run shown.",
         "proof": [("report_maven_build_run42055245961.png", "Maven stage page: log, test counts and coverage (run 42055245961)")]},
        {"id": "sonar", "name": "Code quality gate", "technique": "Static analysis with a blocking quality gate",
         "tool": "SonarQube Community Build", "gate": "The pipeline waits for the gate and fails if it fails", "report": "quality/report.html",
         "status": "verified", "note": "The blocking gate passed on the GitHub-hosted runner. The earlier Azure baseline recorded 11 issues, including six HIGH entity-binding findings.",
         "proof": [(f"{HOSTED_SHOT}sonarqube-project-dashboard.png", f"SonarQube project dashboard on the hosted runner (run {HOSTED_RUN})"),
                   (f"{HOSTED_SHOT}sonarqube-issues.png", f"SonarQube issue list for the same analysis (run {HOSTED_RUN})"),
                   ("sonarqube_first_baseline_findings.png", "First baseline: 41.5% coverage and 11 issues (run 39883066388)"),
                   ("sonarqube_entity_binding_findings.png", "Six HIGH java:S4684 findings in the controllers from the earlier Azure baseline")]},
        {"id": "nexus", "name": "Artifact repository", "technique": "Publish the tested JAR, then compare the stored checksum with the tested JAR",
         "tool": "Sonatype Nexus", "gate": "A different stored checksum fails the stage", "report": "artifact/report.html",
         "status": "verified", "note": "The hosted run's artifact report records matching SHA-1 checksums for the published snapshot and the tested JAR. The screenshot captured Nexus's sign-in screen when the runner opened the snapshot browser.",
         "proof": [(f"{HOSTED_SHOT}nexus-maven-snapshots.png", f"Nexus sign-in screen captured while opening the snapshot browser (run {HOSTED_RUN})"),
                   ("nexus_default_encryption_key_before.png", "Earlier real finding: Nexus used the default encryption key"),
                   ("nexus_private_encryption_key_after.png", "After remediation with a private key")]},
        {"id": "image", "name": "Image build and vulnerability gate", "technique": "Build a non-root image from the tested JAR and scan the final image. The parallel commit workflow also smoke-tests the image on ephemeral k3s.",
         "tool": "Docker, Trivy, k3d", "gate": "Any HIGH/CRITICAL finding fails, including unfixed ones", "report": "image/report.html",
         "status": "verified", "note": "An earlier run was blocked by 11 HIGH/CRITICAL findings; see SECURITY-GATE-CASE-STUDY.md.",
         "proof": [("report_image_trivy_run42055245961.png", "Image stage page: build facts, k3s smoke test and Trivy result, 0 HIGH/CRITICAL (run 42055245961)")]},
        {"id": "registry", "name": "Image registry", "technique": "Push the scanned image and deploy by immutable digest",
         "tool": "Docker Distribution registry (runner loopback)", "gate": "The digest must belong to the pushed image", "report": "registry/report.html",
         "status": "verified", "note": "The hosted run publishes to localhost:5000. Its report records the push log and digest. The screenshot records the earlier Azure registry push.",
         "proof": [("report_acr_registry_run42108525318.png", "Historical Azure registry push and immutable digest (run 42108525318)")]},
        {"id": "deploy", "name": "Acceptance lab", "technique": "Start the lab's Compose stack on the runner and verify readiness before testing TCP exposure",
         "tool": "Docker Compose, Spring Boot, MySQL", "gate": "The running image must match the scanned digest and a database-backed API request must pass", "report": "deploy/report.html",
         "status": "verified", "note": "The Compose stack runs for the duration of the job. The first hosted run recorded DEPLOY_SUCCEEDED and verified a database-backed API response.",
         "proof": [(f"{HOSTED_SHOT}swagger-api.png", f"Swagger UI for the API deployed on the runner (run {HOSTED_RUN})"),
                   ("coursework_first_compose_failure.png", "Historical Azure Compose startup failure, repaired before the later Azure run (run 39883066388)")]},
        {"id": "nmap", "name": "Network acceptance", "technique": "Scan the runner's primary IPv4 address and loopback against a TCP allowlist",
         "tool": "Nmap", "gate": "Unexpected open, missing required or incomplete scans fail", "report": "acceptance/report.html",
         "status": "verified", "note": "The hosted run checks 1,041 TCP ports per target. The primary interface allows only the runner's OpenSSH listener. Loopback requires Grafana, the registry, the API and Prometheus, and also allows OpenSSH.",
         "proof": [("report_nmap_acceptance_run42016218929.png", "Historical Azure acceptance from public and private viewpoints (run 42016218929)")]},
    ]},
    {"phase": "C. Production", "stages": [
        {"id": "production", "name": "Production smoke test", "technique": "After Nmap passes, verify the running image digest and a database-backed API response",
         "tool": "Docker image inspection, Spring Boot API, MySQL", "gate": "The running image must match the scanned digest and the API must return a JSON array",
         "report": "production/report.html",
         "status": "verified", "note": "The lab demonstrates a production smoke test on the same Compose stack. The first hosted run recorded the digest and API checks in deploy/report.html. The course-aligned workflow also records a dedicated smoke result after Nmap.",
         "proof": [("report_compose_deploy_run42108525318.png", "Historical Azure Compose verification of the scanned image (run 42108525318)")]},
    ]},
    {"phase": "D. Operations", "stages": [
        {"id": "monitoring", "name": "Monitoring: Prometheus and Grafana", "technique": "Verify scrape targets, sample real queries after light API traffic, list provisioned dashboards",
         "tool": "Prometheus, Node Exporter, Grafana", "gate": "API and runner exporter UP, Grafana database healthy, both dashboards provisioned", "report": "monitoring/, prometheus/, grafana/ report.html",
         "status": "verified", "note": "The hosted run recorded both scrape targets UP and 30 successful read-only requests. The combined report includes the native metrics and the UI screenshots below.",
         "proof": [(f"{HOSTED_SHOT}prometheus-targets.png", f"Prometheus targets for the application and runner exporter (run {HOSTED_RUN})"),
                   (f"{HOSTED_SHOT}grafana-student-api-dashboard.png", f"Grafana dashboard for the student API (run {HOSTED_RUN})"),
                   (f"{HOSTED_SHOT}grafana-host-dashboard.png", f"Grafana host dashboard showing the GitHub runner exporter (run {HOSTED_RUN})")]},
    ]},
    {"phase": "Supporting controls", "stages": [
        {"id": "dependabot", "name": "Dependency maintenance", "technique": "Report weekly version-update PRs for five ecosystems and the status of GitHub's vulnerability alerts",
         "tool": "Dependabot, GitHub REST API", "gate": "Reported, not blocking: disabled alerts, HIGH/CRITICAL alerts and failing update PRs are highlighted for attention", "report": "dependabot/report.html",
         "status": "verified", "note": "The first CI run found 13 open update PRs (8 major or variant changes, all passing CI, oldest 19 days) and Dependabot security alerts DISABLED on the repository (GitHub answered HTTP 403, alerts disabled). Status is attention, not passed: enabling alerts is a repository setting for the owner.",
         "proof": [("report_dependabot_run43047106961.png", "Dependabot stage page: alerts-disabled finding, 13 update PRs with major and variant changes highlighted (run 43047106961, pull request 27, 11 Nov 2026)")]},
        {"id": "email", "name": "Email notification", "technique": "Status, per-stage results and the run link sent at the end of every master run",
         "tool": "SMTP over STARTTLS", "gate": "Runs even after failure or cancellation", "report": "the email, and the job in the run graph",
         "status": "verified", "note": "The inbox screenshot verifies receipt of the commit-security notification for run 43080079320. The course-aligned full pipeline run 43082725820 separately records SMTP acceptance for its status message.",
         "proof": [("email_commit_security_run43080079320.png", "Inbox evidence for the commit-security notification (run 43080079320). The address header is obscured."),
                   ("run_coursework_master_42108525318.png", "Historical Azure run with a successful email job (run 42108525318)")]},
    ]},
]

PENDING_PROOF = [
    "Dependabot security alerts are disabled on the repository: enable them, then the report will list real alert findings",
]
LEGACY = [("screenshot1_getting_started.png", "Jenkins plugin installation"), ("screenshot2_dashboard.png", "Jenkins dashboard"),
          ("screenshot3_sonarqube_interface.png", "SonarQube interface"), ("screenshot4_docker_containers_running.png", "Containers running"),
          ("screenshot5_sonarqube_29%_coverage.png", "SonarQube 29% coverage"), ("screenshot6_minikube_start.png", "Minikube start"),
          ("screenshot7_minikube_ready.png", "Minikube ready"), ("screenshot8_jenkins_green_pipeline.png", "Green Jenkins pipeline"),
          ("screenshot9_kubectl_getpods.png", "kubectl get pods"), ("screenshot10_kubectl_get_svc.png", "kubectl get svc"),
          ("screenshot11_Swagger_UI.png", "Swagger UI")]


def image(name):
    data = base64.b64encode((SHOTS / name).read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def figure(name, caption, esc=html.escape):
    return f"<figure><img src='{image(name)}' alt='{esc(caption)}'><figcaption>{esc(caption)}</figcaption></figure>"


def referenced_files():
    return {name for phase in CATALOG for stage in phase["stages"] for name, _ in stage["proof"]} | {name for name, _ in LEGACY}


def excerpt_log(match):
    start, text, end = match.groups()
    lines = text.splitlines()
    if len(lines) <= 42:
        return match[0]
    gap = f"\n[Full log in the attached ZIP. {len(lines) - 32} lines omitted here.]\n"
    return start + "\n".join(lines[:8]) + gap + "\n".join(lines[-24:]) + end


def tool_appendix(archive):
    with ZipFile(archive) as bundle:
        if f"/actions/runs/{EVIDENCE_RUN}" not in bundle.read("index.html").decode("utf-8"):
            raise ValueError(f"The tool report archive must come from GitHub Actions run {EVIDENCE_RUN}")
        pages = []
        for folder, title in TOOL_REPORTS:
            path = f"{folder}/report.html"
            source = bundle.read(path).decode("utf-8")
            start = source.index("<h1>")
            end = source.rindex("</html>")
            # Keep the original measurements and tables. Long logs remain complete in the ZIP.
            content = source[start:end].replace("<h1>", "<h3>", 1).replace("</h1>", "</h3>", 1)
            content = content.replace("href='../index.html'", "href='#tool-reports'")
            content = re.sub(r'href="(?:public|private)/[^"]+"', f'href="{EVIDENCE_ARTIFACT}"', content)
            content = re.sub(r"(<pre style='white-space:pre-wrap[^']*'>)(.*?)(</pre>)", excerpt_log, content, flags=re.DOTALL)
            pages.append(f"<section class='tool-report' id='report-{folder}'>{content}</section>")
    links = "".join(f"<li><a href='#report-{folder}'>{html.escape(title)}</a></li>" for folder, title in TOOL_REPORTS)
    return (f"<section class='tool-index' id='tool-reports'><h2>Appendix B. Tool reports from the hosted run</h2>"
            f"<p>These are the original report pages from the <a href='{EVIDENCE_ARTIFACT}'>combined evidence archive</a> "
            f"for <a href='{RUN}{EVIDENCE_RUN}'>run {EVIDENCE_RUN}</a>, with excerpts from long console logs. For the original JSON, XML, full logs and screenshots, "
            "open the ZIP attached to this PDF or download it from GitHub.</p>"
            f"<ul>{links}</ul></section>" + "\n".join(pages))


def build(commit="unknown", archive=None, prior_reports=()):
    esc = html.escape
    badge = {"verified": "Verified in a real run", "partial": "Partly verified", "pending": "Implemented, not yet run live"}
    out = ["<!doctype html><html lang='en'><meta charset='utf-8'><title>DevSecOps pipeline: final report</title>",
           "<style>body{font:16px/1.5 Arial,sans-serif;color:#172332;max-width:1000px;margin:36px auto;padding:0 24px}h1{font-size:32px}h2{border-bottom:2px solid #dde5ec;padding-bottom:6px;margin-top:40px}"
           "table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid #bbb;padding:7px;text-align:left;vertical-align:top}th{background:#eef3f7}"
           "figure{margin:14px 0;page-break-inside:avoid}img{max-width:100%;border:1px solid #bbb}figcaption{font-size:13px;color:#495a6a}"
           ".verified{color:#116329;font-weight:bold}.partial{color:#9a6700;font-weight:bold}.pending{color:#a40e26;font-weight:bold}"
           ".stage{margin-top:26px}h3,h4{page-break-after:avoid}code{overflow-wrap:anywhere}"
           ".tool-report h2{font-size:14px;margin-top:16px}.tool-report pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:8.5px}"
           ".tool-report svg{max-width:100%;height:auto}.tool-report table{overflow-wrap:anywhere}"
           "@page{size:A4;margin:10mm 10mm 14mm;@bottom-right{content:counter(page) ' / ' counter(pages);font:9px Arial,sans-serif;color:#495a6a}}"
           "@media print{body{margin:0;max-width:none;font-size:11px}h2{page-break-after:avoid}table{table-layout:fixed;font-size:10px}tr{break-inside:avoid}td,th{padding:4px}"
           "figure{margin:9px 0 12px}figure img{display:block;max-height:176mm}figcaption{font-size:10px;margin-top:3px}"
           ".tool-index,.tool-report,.prior-reports{break-before:page}.tool-report svg{break-inside:avoid}}</style>",
           "<h1>DevSecOps pipeline: final report</h1>",
           f"<p>Oussama Koudhai · 4NIDS6, Esprit<br>Spring Boot student-management API<br><a href='{REPO}'>Project repository</a><br>"
           f"Report built {date.today().isoformat()} from revision <code>{esc(commit)}</code>.</p>",
           "<h2>First GitHub-hosted run on master</h2>",
           f"<p>The pipeline passed on 11 November 2026 after <a href='{REPO}/pull/28'>PR #28</a> merged. "
           "SonarQube, Nexus, the image registry, the Compose stack and monitoring all ran on the disposable GitHub-hosted runner. "
           "Nmap acceptance passed, both Prometheus targets were UP, and all 30 sample API requests succeeded. "
           f"The seven UI screenshots below come from this run. <a href='{RUN}{HOSTED_RUN}'>GitHub Actions run {HOSTED_RUN}</a> · "
           f"<a href='{HOSTED_ARTIFACT}'>Combined report artifact</a></p>",
           f"<p>The <a href='{RUN}{AZURE_RUN}'>5 November Azure run {AZURE_RUN}</a> remains the historical evidence for delivery to an Azure VM. "
           "The Azure workflow is now manually triggered. The hosted workflow runs on pushes to <code>master</code> and pull requests targeting it.</p>",
           "<h2>How the lab maps to the course</h2><p>Development runs the early security checks. Acceptance builds the artifact, starts a disposable Compose test environment and checks TCP exposure with Nmap. "
           "Production smoke testing then verifies the scanned digest and database-backed API on that same stack. Operations uses Prometheus and Grafana while the lab is running. "
           "The job demonstrates these practices without a separate production promotion or an always-on service.</p>",
           ]
    if archive:
        out.append("<p><a href='#tool-reports'>Appendix B</a> contains the hosted tool reports and the original evidence ZIP.</p>")
    if prior_reports:
        out.append("<p><a href='#prior-reports'>Appendix C</a> contains the earlier standalone assessment PDFs.</p>")
    out.append("<h2>Pipeline at a glance</h2><table><colgroup><col style='width:4%'><col style='width:13%'><col style='width:24%'><col style='width:15%'><col style='width:19%'><col style='width:12%'><col style='width:13%'></colgroup><thead><tr><th>#</th><th>Stage</th><th>Technique</th><th>Tool</th><th>Blocks the pipeline when</th><th>Report</th><th>Status</th></tr></thead><tbody>")
    number = 0
    for phase in CATALOG:
        out.append(f"<tr><th colspan='7'>{esc(phase['phase'])}</th></tr>")
        for stage in phase["stages"]:
            number += 1
            stage["number"] = number
            out.append(f"<tr><td>{number}</td><td>{esc(stage['name'])}</td><td>{esc(stage['technique'])}</td><td>{esc(stage['tool'])}</td>"
                       f"<td>{esc(stage['gate'])}</td><td><code>{esc(stage['report'])}</code></td><td class='{stage['status']}'>{esc(badge[stage['status']])}</td></tr>")
    out.append("</tbody></table>")
    out.append("<h2>Stage by stage, with proof</h2>")
    for phase in CATALOG:
        out.append(f"<h3>{esc(phase['phase'])}</h3>")
        for stage in phase["stages"]:
            out.append(f"<div class='stage'><h4>{stage['number']}. {esc(stage['name'])} <span class='{stage['status']}'>[{esc(badge[stage['status']])}]</span></h4>"
                       f"<p><strong>Technique:</strong> {esc(stage['technique'])}<br><strong>Tool:</strong> {esc(stage['tool'])}<br>"
                       f"<strong>Blocks the pipeline when:</strong> {esc(stage['gate'])}<br><strong>Report:</strong> <code>{esc(stage['report'])}</code></p>")
            if stage["note"]:
                out.append(f"<p><em>{esc(stage['note'])}</em></p>")
            out += [figure(name, caption) for name, caption in stage["proof"]] or ["<p><em>No screenshot of this stage exists yet.</em></p>"]
            out.append("</div>")
    out.append("<h2>Real failures found and fixed</h2><ul>"
               "<li>Trivy blocked the first image with 11 HIGH/CRITICAL findings; fixed by upgrading Spring Boot and Jackson (SECURITY-GATE-CASE-STUDY.md).</li>"
               "<li>Checkov rejected public HTTP port 80 (CKV_AZURE_160); the port was closed and the rescan passed (screenshots under Infrastructure-as-code policy).</li>"
               "<li>The first Compose deployment failed on a missing localhost port mapping and config file permissions; repaired and re-run (see Deployment).</li>"
               "<li>Nexus reported the default encryption key; replaced with a private key (see Artifact repository).</li>"
               f"<li>The <a href='{RUN}43067552466'>first hosted PR run</a> stopped at Nmap when it detected the runner's OpenSSH listener. "
               "The runner policy now allows TCP 22 and continues to enforce loopback-only access for lab services.</li>"
               "<li>The historical Azure SonarQube baseline recorded six HIGH entity-binding findings.</li></ul>")
    out.append("<h2>Not yet proven (to capture)</h2><ul>" + "".join(f"<li>{esc(item)}</li>" for item in PENDING_PROOF) + "</ul>")
    out.append(f"<h2>How to open the evidence</h2><p>From <a href='{HOSTED_ARTIFACT}'>the hosted run's artifacts</a>, download "
               "<strong>devsecops-security-reports</strong>, extract it and open <code>index.html</code>. "
               "The index links to stage reports, original measurements and the screenshot gallery. The runner and its services stop after the job.</p>")
    out.append("<h2>Appendix A. The original Jenkins and Minikube pipeline</h2><p>The project started with this school pipeline, preserved in documentation/LEGACY-JENKINS-MINIKUBE.md.</p>")
    out += [figure(name, caption) for name, caption in LEGACY]
    if archive:
        out.append(tool_appendix(archive))
    if prior_reports:
        out.append("<section class='prior-reports' id='prior-reports'><h2>Appendix C. Historical assessment PDFs</h2>"
                   "<p>The following reports retain their original dates, pages and measurements.</p><ul>" +
                   "".join(f"<li>{esc(path.stem)}</li>" for path in prior_reports) + "</ul></section>")
    out.append("</html>")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", action="store_true")
    parser.add_argument("--chrome", default="C:/Program Files/Google/Chrome/Application/chrome.exe")
    parser.add_argument("--tool-reports", type=Path, help="Combined evidence ZIP from the course-aligned hosted run")
    parser.add_argument("--append-pdf", type=Path, action="append", default=[], help="Historical PDF to append (repeatable)")
    args = parser.parse_args()
    if args.append_pdf and not args.pdf:
        parser.error("--append-pdf requires --pdf")
    missing = sorted(name for name in referenced_files() if not (SHOTS / name).is_file())
    if missing:
        raise SystemExit("Missing screenshots: " + ", ".join(missing))
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip() or "unknown"
    target = ROOT / "documentation/FINAL-REPORT.html"
    target.write_text(build(commit, args.tool_reports, args.append_pdf), encoding="utf-8")
    print(f"Wrote {target}")
    if args.pdf:
        pdf = ROOT / "documentation/FINAL-REPORT.pdf"
        with tempfile.TemporaryDirectory(dir=pdf.parent) as directory:
            work = Path(directory)
            draft = work / "report.pdf"
            subprocess.run([args.chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                            "--generate-pdf-document-outline", f"--user-data-dir={work / 'chrome'}",
                            f"--print-to-pdf={draft}", target.as_uri()], capture_output=True, check=True)
            if not draft.is_file() or not draft.stat().st_size:
                raise SystemExit("Chrome did not produce the PDF")
            if args.append_pdf or args.tool_reports:
                import pymupdf

                combined = work / "combined.pdf"
                with pymupdf.open(draft) as report:
                    outline = report.get_toc()
                    for path in args.append_pdf:
                        outline.append([1, path.stem, report.page_count + 1])
                        with pymupdf.open(path) as historical:
                            report.insert_pdf(historical)
                    if args.tool_reports:
                        archive_name = f"devsecops-security-reports-{EVIDENCE_RUN}.zip"
                        report.embfile_add(archive_name, args.tool_reports.read_bytes(), filename=archive_name)
                    report.set_toc(outline)
                    report.save(combined, garbage=4, deflate=True)
                draft = combined
            draft.replace(pdf)
        print(f"Wrote {pdf}")


if __name__ == "__main__":
    sys.exit(main())
