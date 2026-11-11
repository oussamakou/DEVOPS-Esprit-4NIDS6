# Demonstrating the pipeline: every push, every tool, every report

**Status (11 Nov 2026):** the Azure for Students subscription has ended, so the Azure
VMs are offline. Every master push now runs the **whole** sequence on a free
GitHub-hosted runner (`pipeline.yml`): SonarQube, Nexus, a registry, the deployed
stack, Nmap, Prometheus and Grafana exist only for the duration of the run. The
Azure lane (`coursework.yml`) is kept for manual use; its successful run on 5 Nov
(42108525318) remains the evidence of the real cloud deployment.

## What happens on a push

| Push to | Workflow | Stages that run and report |
| --- | --- | --- |
| Any branch or pull request | `devsecops.yml` | Pre-commit replay, Semgrep, Gitleaks, Checkov, Trivy on the POM, Maven + tests + JaCoCo, image build, k3d smoke test, Trivy image gate, Dependabot report, combined report (these are the required checks on `master`) |
| Pull request or `master` | `pipeline.yml` (GitHub-hosted, free) | The same security gates, then 2 Maven, 3 SonarQube with blocking gate, 4 Nexus publish and checksum verify, 5 image build and Trivy, 6 registry push by digest, 7 Docker Compose deployment, 8 Nmap acceptance, 9 monitoring with Prometheus and Grafana, 10 Dependabot, combined report, 11 email (master only) |
| Manual only | `coursework.yml` (Azure) | The same sequence against the Azure VMs, when an Azure subscription is available again |

### What the disposable lane does differently

- It uses the lab's own files: `cloud/tools/compose.yml` for SonarQube and Nexus
  (same versions as the Azure tools VM) and `cloud/runtime/compose.yml` for the
  deployment. The image is pushed to a `registry:2` on the runner and deployed by
  immutable digest, exactly as with ACR.
- Each run generates random SonarQube and Nexus admin passwords (masked) and
  accepts the Nexus Community Edition EULA through its API, as the owner chose;
  the accepted disclaimer is saved in the report.
- `security/nmap-policy-runner.json` permits the hosted runner's SSH listener on
  TCP 22 on both scan targets. Lab services must stay off the primary network
  interface. The gate requires Grafana, the registry, the API and Prometheus on
  loopback and blocks any other scanned open port.
- Read-only anonymous browsing is enabled on SonarQube, Nexus and Grafana **inside
  the throwaway runner only**, so headless Chrome can capture real screenshots of
  each tool; they appear in the report's screenshot gallery. The Azure lane keeps
  authentication on.
- Nothing persists after the run: there is no live URL to give the professor.
  Show the run, its report and its screenshots.

Every pipeline workflow ends with an **Email notification** job that waits for all
other jobs and runs even after a failure or cancellation. The message lists each
stage's result and the run link. Pull requests send no email. A master push runs
both `devsecops.yml` and `pipeline.yml`, so it sends two emails with different
subjects.

## Where each tool reports

Every run publishes the artifact **devsecops-security-reports**. Download it,
extract it and open `index.html`: the first table lists every stage with its
tool, outcome, what it measured and a link to its own page. A stage that did not
run says so; it is never shown as passed. The same table appears in the run's
Summary page, and each captured command also adds a line to its job summary.

| Stage | Tool | Page in the report | Original evidence |
| --- | --- | --- | --- |
| Pre-commit and threat model | pre-commit, Gitleaks hook | `precommit/report.html` | hook transcript, `THREAT-MODEL.md` |
| Commit SAST | Semgrep | `sast/report.html` | `semgrep.json`, controlled exercise |
| Secrets | Gitleaks | `secrets/report.html` | redacted `gitleaks.json` |
| Dependencies | Trivy, CycloneDX | `dependencies/report.html` | `dependencies.json`, `sbom.cdx.json` |
| Infrastructure | Terraform, Checkov | `iac/report.html` | JSON, JUnit and logs |
| Build and tests | Maven, Surefire, JaCoCo | `build/report.html` *(new)* | `maven.log`, Surefire XML, JaCoCo HTML/XML |
| Quality gate | SonarQube | `quality/report.html` *(new)* | `sonar.log`, `report-task.txt`, dashboard link |
| Artifact | Nexus | `artifact/report.html` *(new)* | deploy log; checksum of the stored JAR compared with the tested JAR |
| Image | Docker, k3d, Trivy | `image/report.html` *(new)* | build log, `trivy-image.json` |
| Registry | Azure Container Registry | `registry/report.html` *(new)* | push log, immutable digest |
| Deployment | Docker Compose via Run Command | `deploy/report.html` *(new)* | guest output |
| Network acceptance | Nmap | `acceptance/report.html` | XML, `.nmap`, `.gnmap` |
| Monitoring check | API request, scrape targets | `monitoring/report.html` *(new)* | guest output |
| Metrics collection | Prometheus, Node Exporter | `prometheus/report.html` *(new)* | targets, instant values, rule groups |
| Dashboards | Grafana | `grafana/report.html` *(new)* | health, data sources, dashboards, panel data |
| Dependency updates and alerts | Dependabot | `dependabot/report.html` *(new)* | open update PRs with change type, CI state and age; security alerts; configuration |

The Grafana page draws the dashboard's PromQL series from Prometheus
`query_range` as SVG charts. They are labelled as Prometheus data and are **not**
Grafana screenshots.

## Open every dashboard

1. **GitHub Actions run:** repository **Actions** tab, then the run. The Summary
   shows the stage graph, the stage table and the downloadable artifacts.
2. **SonarQube:** the link in the report's "Live tool dashboards" list (the
   `SONAR_HOST_URL` variable). Sign-in is required.
3. **Nexus:** the repository-browser link in the same list. Sign-in is required.
4. **Prometheus and Grafana** are private to the app VM. Open the SSH tunnel
   from your workstation, as in [MONITORING-DEMO.md](MONITORING-DEMO.md):

   ```powershell
   powershell -NoProfile -File C:\Users\oussa\.ssh\student-course-open-dashboards.ps1
   ```

   Then open `http://127.0.0.1:9091/targets` (Prometheus),
   `http://127.0.0.1:3000/d/student-devsecops` and
   `http://127.0.0.1:3000/d/student-vms` (Grafana). The tunnel needs the app VM
   running and your current public IP allowed by the SSH rule. The Grafana
   password is in your private `.ssh/student-course-credentials.md`; do not show it.
5. **Azure portal:** the container registry's repository page shows the pushed digest.
6. **Email:** the status message links back to the run.

## Screenshots

| Screenshot | Status |
| --- | --- |
| Actions run graphs (coursework run 40899036172, Nmap run 42016218929, master run 42020639183) | Captured, `documentation/screenshots/run_*.png` |
| SonarQube first baseline, Nexus encryption key, Compose failure, Checkov failed and passed | Captured earlier, see `EVIDENCE-CAPTURE.md` |
| SonarQube dashboard, Nexus repository, ACR digest, received email | To capture: they need your sign-in |
| Prometheus targets, Grafana dashboards under traffic | To capture: they need the SSH tunnel and your Grafana password |
| The new `index.html` and per-stage pages | To capture after the first successful run on `master` |

## Limits to state honestly

- Maven's `-ntp` flag hides upload lines, so Nexus is verified by comparing the
  repository's published SHA-1 for the newest snapshot with the tested JAR's SHA-1.
- The monitoring step sends about 30 read-only requests to the lab API so the
  request-rate and latency series exist. It is a light sample, not a load test.
- A green run on one commit does not prove a later commit is safe; scanner
  databases change.
- The report shows evidence of what each tool did. It does not replace reading
  the findings, and threat modelling remains a human review.

## Final report

`documentation/FINAL-REPORT.pdf` lists every stage with its technique, tool, blocking
condition, report location and screenshot proof, marks what is still unproven, and
ends with the original Jenkins/Minikube screenshots. Rebuild it after capturing new
screenshots with `python scripts/build-final-report.py --pdf`; the script refuses to
run if a screenshot it cites is missing, and the tests stop a pending stage from
citing proof it does not have.
