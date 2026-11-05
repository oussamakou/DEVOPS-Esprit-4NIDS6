# Demonstrating the pipeline: every push, every tool, every report

**Status:** implemented and unit-tested offline (`scripts/test-stage-reports.py`).
The first live run of the new per-stage reports is still to be done; until a run
has completed, treat the parts marked *new* below as unverified in Azure.

## What happens on a push

| Push to | Workflow | Stages that run and report |
| --- | --- | --- |
| Any branch or pull request | `devsecops.yml` | Pre-commit replay, Semgrep, Gitleaks, Checkov, Trivy on the POM, Maven + tests + JaCoCo, image build, k3d smoke test, Trivy image gate, combined report |
| `master` | the same, plus `coursework.yml` *(new trigger)* | All of the above, then SonarQube, Nexus, image build and scan, ACR, Docker Compose on Azure, Nmap, monitoring, Prometheus and Grafana evidence, combined report, email |

`coursework.yml` also stays manually dispatchable. Because it now runs on every
push to `master`, merging a pull request deploys to the Azure lab VM and sends the
status email. Pull requests never reach Azure. The `azure-lab` environment still
limits deployment to `master`.

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
