# Evidence, not estimates

Do not commit scanner reports or Terraform plans blindly; they can contain private data.
The workflow stores redacted Gitleaks results, Checkov JUnit XML, Trivy JSON,
test/coverage reports and deployment output as short-lived GitHub artifacts.
Download evidence you want to retain before its retention period expires.

| Claim | Required evidence | Current status |
| --- | --- | --- |
| Azure provisioned by Terraform | Reviewed plan, apply output, resource inventory | Coursework workspace applied by the owner (19 added, 0 changed, 0 destroyed, as recorded in COURSEWORK-PIPELINE.md). The plan/apply log is not saved in this repository. Both VMs answered the Nmap acceptance run 42016218929 on 2026-11-05 |
| Six security/build/deploy stages (k3s workflow `devsecops.yml`) | Workflow run URL and gate reports | Five stages passed; k3s deployment intentionally disabled (`AZURE_DEPLOY_ENABLED=false`) |
| HIGH/CRITICAL blocked delivery | Actual failing report and a later passing report for the fix | Demonstrated before publication; see the security case study |
| Faster deployment with caches | Multiple comparable cold/warm run timings | Not measured |
| Smaller runtime image | Same-method size measurements before and after | Not measured |
| Metrics monitored | Prometheus target UP and Grafana charts under API traffic | Ephemeral k3s target UP verified; Azure Compose Prometheus target UP verified on the VM (COMPOSE-STARTUP-CASE-STUDY.md). Grafana dashboards under real API traffic are not yet captured as screenshots |
| Coursework sequence | SonarQube, Nexus, ACR, Azure Compose, monitoring and received email | Provisioned and run: the delivery and email jobs succeeded in runs 39886514168 (23 Oct) and 40899036172 (29 Oct); the first run 39883066388 failed and is documented. SMTP accepted the message, but inbox receipt is not confirmed |
| Nmap network acceptance | Passing gate plus original XML/text reports | Standalone run 42016218929 passed on 2026-11-05; the earlier run 42013118446 failed and is documented in NMAP-ACCEPTANCE.md |
| Full integrated pipeline (deploy, Nmap, monitoring, combined reports, email) | One successful `coursework.yml` run after the Nmap and node-exporter changes | **Not yet run.** The last full run (40899036172) predates both changes |
| Commit security | Hooks, Semgrep, Java dependency report and SBOM | Passed in hosted run 39805591559 |
| Coursework infrastructure error and fix | Failed CKV_AZURE_160 run and passing rescan | Runs 39805052147 / 39805591559; screenshots in documentation/screenshots |

Use `python scripts/measure-workflow.py OWNER/REPO RUN_ID` after GitHub CLI login.
Record at least three cold-cache and three warm-cache runs of the same commit.
Use workflow_dispatch with cold_cache enabled/disabled. The reported wall time
includes queueing/artifact transfers as well as execution. Report the median and
range, runner type and cache state. Never sum parallel job durations to claim wall time.

Cloud-init / Terraform time is not part of application delivery timing. Do not compare
an initial infrastructure install with a later application-only deployment.
