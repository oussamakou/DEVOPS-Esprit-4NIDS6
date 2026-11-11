# Demonstrating the pipeline: every push, every tool, every report

**Status (11 Nov 2026):** the Azure for Students subscription has ended, so the Azure
VMs are offline. Every master push now runs the **whole** sequence on a free
GitHub-hosted runner (`pipeline.yml`): SonarQube, Nexus, a registry, the deployed
stack, Nmap, Prometheus and Grafana exist only for the duration of the run. The
Azure workflow (`coursework.yml`) is kept for manual use. The
[5 November Azure run](https://github.com/oussamakou/DEVOPS-Esprit-4NIDS6/actions/runs/42108525318)
remains the evidence of delivery to an Azure VM.

## What happens on a push

| Push to | Workflow | Stages that run and report |
| --- | --- | --- |
| Pull request to `master` or push to `master` | `devsecops.yml` | Pre-commit replay, Semgrep, Gitleaks, Checkov, Trivy on the POM, Maven + tests + JaCoCo, image build, k3d smoke test, Trivy image gate, Dependabot report, combined report |
| Pull request to `master` or push to `master` | `pipeline.yml` (GitHub-hosted, free) | Development gates, then Maven, SonarQube, Nexus, image scanning, registry push by digest, the Compose acceptance lab, Nmap, production smoke test, Operations monitoring, Dependabot, combined report, and email on `master` |
| Manual only | `coursework.yml` (Azure) | The historical delivery workflow for the Azure VMs, when an Azure subscription is available again |

## Course phases in the hosted lab

| Phase | Evidence to show |
| --- | --- |
| Development | Manual STRIDE threat model, pre-commit hooks, Semgrep SAST, Gitleaks, Checkov, and Trivy dependency scanning before Maven compilation |
| Acceptance | Build and scan the release artifact, start a disposable Compose test stack, and use Nmap to enforce the TCP exposure policy |
| Production | After Nmap passes, verify the scanned digest on the running container and exercise the database-backed API. This is a smoke test on the same lab stack. |
| Operations | Verify Prometheus scrapes and Grafana dashboards during the runner job, including both targets and sample API traffic |

The hosted workflow demonstrates the four phases on one temporary stack. Dependabot
reports dependency maintenance across the lifecycle. The status email links to the
run. The Azure run above provides the historical VM deployment evidence.

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
| Registry | Docker Distribution registry | `registry/report.html` | push log, immutable digest |
| Acceptance lab | Docker Compose on the runner | `deploy/report.html` | deployment log and readiness check |
| Network acceptance | Nmap | `acceptance/report.html` | XML, `.nmap`, `.gnmap` |
| Production smoke test | Docker image inspection, database-backed API request | `production/report.html` | smoke test log and scanned digest. In the first hosted run, the digest and API checks are in `deploy/report.html`. |
| Operations monitoring | API and scrape-target health checks | `monitoring/report.html` | monitoring check log |
| Metrics collection | Prometheus, Node Exporter | `prometheus/report.html` *(new)* | targets, instant values, rule groups |
| Dashboards | Grafana | `grafana/report.html` *(new)* | health, data sources, dashboards, panel data |
| Dependency maintenance | Dependabot | `dependabot/report.html` | open update PRs, CI status, security alert status, and configuration |

The Grafana page draws the dashboard's PromQL series from Prometheus
`query_range` as SVG charts. They are labelled as Prometheus data and are **not**
Grafana screenshots.

## Open the hosted run and screenshots

1. Open the [first GitHub-hosted run on `master`](https://github.com/oussamakou/DEVOPS-Esprit-4NIDS6/actions/runs/43076300738).
   The Summary shows the job graph and stage results.
2. Download the [combined report artifact](https://github.com/oussamakou/DEVOPS-Esprit-4NIDS6/actions/runs/43076300738/artifacts/13881273531)
   and open `index.html`. Its gallery contains seven screenshots covering SonarQube,
   Nexus, Prometheus, both Grafana dashboards and Swagger. The Nexus capture
   shows its sign-in screen. Open `artifact/report.html` for the verified
   snapshot checksum. The tools stop when the runner job ends.
3. Open the [final coursework report](FINAL-REPORT.pdf) for a printable copy
   with the screenshots. [Monitoring demo](MONITORING-DEMO.md) documents the
   SSH tunnel for the historical Azure setup.

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
