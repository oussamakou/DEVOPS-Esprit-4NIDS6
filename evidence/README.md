# Evidence, not estimates

Do not commit scanner reports or Terraform plans blindly; they can contain private data.
The workflow stores redacted Gitleaks results, Checkov JUnit XML, Trivy JSON,
test/coverage reports and deployment output as short-lived GitHub artifacts.
Download evidence you want to retain before its retention period expires.

| Claim | Required evidence | Current status |
| --- | --- | --- |
| Azure provisioned by Terraform | Reviewed plan, apply output, resource inventory | Not deployed |
| Six security/build/deploy stages | Workflow run URL and gate reports | Five stages passed; Azure deployment intentionally disabled |
| HIGH/CRITICAL blocked delivery | Actual failing report and a later passing report for the fix | Demonstrated before publication; see the security case study |
| Faster deployment with caches | Multiple comparable cold/warm run timings | Not measured |
| Smaller runtime image | Same-method size measurements before and after | Not measured |
| Metrics monitored | Prometheus target UP and Grafana charts under API traffic | Ephemeral k3s target UP verified; Azure/dashboard visual verification pending |
| Coursework sequence | SonarQube, Nexus, ACR, Azure Compose, monitoring and received email | Workflow/setup prepared; new cloud services are not provisioned or verified yet |
| Commit security | Hooks, Semgrep, Java dependency report and SBOM | Passed in hosted run 39805591559 |
| Coursework infrastructure error and fix | Failed CKV_AZURE_160 run and passing rescan | Runs 39805052147 / 39805591559; screenshots in documentation/screenshots |

Use `python scripts/measure-workflow.py OWNER/REPO RUN_ID` after GitHub CLI login.
Record at least three cold-cache and three warm-cache runs of the same commit.
Use workflow_dispatch with cold_cache enabled/disabled. The reported wall time
includes queueing/artifact transfers as well as execution. Report the median and
range, runner type and cache state. Never sum parallel job durations to claim wall time.

Cloud-init / Terraform time is not part of application delivery timing. Do not compare
an initial infrastructure install with a later application-only deployment.
