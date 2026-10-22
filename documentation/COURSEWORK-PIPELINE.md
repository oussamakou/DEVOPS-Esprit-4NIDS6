# Azure coursework pipeline

The coursework dashboard is GitHub Actions. All builds run on hosted Linux runners.
The app, MySQL, Prometheus and Grafana run with Docker Compose on Azure, while
SonarQube Community Build, PostgreSQL and Nexus run on a separate Azure tools VM.
No local VM, Vagrant or working Docker Desktop is needed.

## What each stage does

| Stage in `coursework.yml` | Tool and result |
| --- | --- |
| 1. Checkout Git | Fetch the exact Git commit with history |
| 2. Compile Maven | Compile, run tests, package the JAR, generate JaCoCo coverage |
| Commit gates | Re-run hooks, scan Git history with Gitleaks, run Semgrep SAST and Trivy dependency scanning; create a CycloneDX SBOM |
| 3. SonarQube | Publish analysis and wait for a blocking quality gate |
| 4. Nexus | Upload the exact tested JAR with its POM to a hosted Maven snapshots repository |
| 5. Build image | Build from that same JAR, then reject HIGH/CRITICAL image vulnerabilities |
| 6. Deploy image | Publish the scanned image to Azure Container Registry and resolve its immutable digest |
| 7. Docker Compose | Azure Run Command pulls that digest using the VM's managed identity and starts the application stack |
| 8. Monitoring | Verify the API/database request, actual running image, Prometheus target UP and Grafana health |
| 9. Email | Send the success/failure status and Actions URL via authenticated SMTP with STARTTLS |

The numbered stages are named steps within the delivery job so they share the same
tested artifact. Email is an independent job that can run after delivery failure.
Email is explicitly skipped until repository variable `EMAIL_ENABLED=true` is set.
The workflow is manually dispatched **on master**, uses the `azure-lab` environment,
and fails on missing cloud settings; unconfigured external services never count as
passing. Restrict environment deployment branches to master and configure approval
protection as appropriate for the repository plan.

The existing `devsecops.yml` remains the automatic push/PR security workflow with an
optional earlier k3s deployment. Keep `AZURE_DEPLOY_ENABLED=false` for the Compose lab.
This separates fast commit feedback from delivery that requires configured servers.

## Pre-commit and commit security

On Windows (Docker is not needed):

```powershell
python -m venv .tools/hooks-venv
.tools/hooks-venv/Scripts/python.exe -m pip install -r requirements-security.txt
python scripts/install-tools.py gitleaks
.tools/hooks-venv/Scripts/python.exe -m pre_commit install
.tools/hooks-venv/Scripts/python.exe -m pre_commit run --all-files
```

The hooks validate YAML/XML, reject merge markers/private-key headers, and run
Gitleaks against the **staged** Git snapshot. Hook installation is local and must be
repeated by every contributor. CI repeats file checks and independently scans the
full available history, so bypassing a workstation hook does not bypass CI.

Semgrep runs after a push/PR on Linux; the local rules cover selected command
execution, concatenated SQL and TLS-verification patterns. This is deliberately
limited SAST coverage, supplemented by SonarQube at delivery. Trivy inventories the
packaged Java dependencies and blocks HIGH/CRITICAL vulnerabilities without an
ignore-unfixed shortcut. Dependabot proposes weekly Maven, Actions, Python, Docker
and Terraform updates; update PRs must still pass tests and scans.

Threat modeling is a human design activity before coding. Review
[THREAT-MODEL.md](THREAT-MODEL.md) for assets, boundaries, STRIDE scenarios and open
risks, then update it when the architecture changes.

## Prepare resources in Azure Cloud Shell

The enabled Azure for Students subscription is usable, but VM family quota, regional
availability and current student credit must be checked before applying. The tools
VM baseline is 4 vCPU / 16 GB plus a 128 GB disk; the application uses 2 vCPU / 4 GB.
These are billable resources. This project has not yet demonstrated a successful
deployment of these new Compose services.

The confirmed France Central quota is 6 total regional vCPUs, 4 Standard BS vCPUs,
4 Standard DSv4 vCPUs and **zero Standard DSv5 vCPUs**. The coursework defaults are
therefore `Standard_B2s` (app: 2 vCPUs / 4 GiB) plus `Standard_D4s_v4` (tools:
4 vCPUs / 16 GiB), using all 6 regional vCPUs. The earlier D4s_v5 choice would
exceed the family quota. Quota does not guarantee SKU eligibility or available
capacity: the preparation script now checks subscription SKU restrictions before
generating inputs. It saves the returned restrictions in ignored `.tools/azure-skus.json`.
Optional `COURSE_LOCATION`, `COURSE_APP_SIZE` and `COURSE_TOOLS_SIZE` environment
variables override the defaults; review that region's quota and memory needs again.
Preparation prints seven numbered phases. Account/provider requests time out after
120 seconds; the combined VM SKU query times out after 180 seconds. If preparation
stops, capture its phase and error. From the existing checkout, update with
`git pull --ff-only`, then save a rerun with `mkdir -p .tools` and
`bash scripts/prepare-azure-course.sh YOUR_WORKSTATION_PUBLIC_IPV4/32 2>&1 | tee .tools/azure-prepare.log`.

Use the coursework branch until the PR is merged:

```bash
git clone --branch codex/azure-devsecops https://github.com/oussamakou/DEVOPS-Esprit-4NIDS6.git student-course
cd student-course
az account show --query '{Name:name,State:state}' -o table
az provider register --namespace Microsoft.Compute --wait
az provider register --namespace Microsoft.Network --wait
az provider register --namespace Microsoft.ContainerRegistry --wait
az vm list-usage --location francecentral -o table
bash scripts/prepare-azure-course.sh YOUR_WORKSTATION_PUBLIC_IPV4/32
```

Use the public IPv4 of the computer from which you will SSH, **not** Cloud Shell's
outbound address. The script reads the signed-in subscription, creates a separate
`coursework` Terraform workspace, generates an SSH key if needed, and saves a plan.
Prefer setting `COURSE_PUBLIC_KEY` in Cloud Shell to your workstation's existing
SSH **public** key before running it. If you use the generated Cloud Shell key,
download the private key securely to your workstation using Cloud Shell's file
download control; never paste it into chat, Git or screenshots. The /32 rule permits
your workstation, so SSH from Cloud Shell itself is not automatically permitted.
It does not apply the plan. Keep Terraform state and the SSH private key in persistent
Cloud Shell storage; ephemeral Cloud Shell sessions are insufficient for recovery.
The generated `.tfvars.json`, plans and private keys are ignored by Git.
An empty quota table does not mean unlimited quota: this subscription initially
reported `Microsoft.Compute` as `NotRegistered`. Register Compute first, wait for
`Registered`, and then check the regional and VM-family quotas again. Registration
itself does not create the application resources.

After reviewing the plan and checking quota/credit:

```bash
.tools/terraform -chdir=terraform apply coursework.tfplan
.tools/terraform -chdir=terraform output
```

Do not change an existing k3s VM's runtime in place: cloud-init changes can replace
the VM. The coursework workspace and distinct resource prefix avoid taking over
the earlier lab. No additional public app port is opened for Compose; use SSH.

## Bootstrap the tools securely

Get `tools_public_ip`, `tools_fqdn` and `public_ip` from Terraform outputs. The tools
VM has its own Azure DNS hostname. Sonar uses HTTPS 443; Nexus uses HTTPS 8443 on
the same hostname. Caddy obtains certificates using TLS-ALPN on port 443; public
HTTP port 80 remains closed. No purchased domain
is needed. Caddy's HTTPS profile is disabled during initial admin setup.

Copy this checkout to the tools VM, or clone the branch there, then:

```bash
# On the tools VM after SSH (use the key created by the preparation script):
sudo cloud-init status --wait
sudo bash scripts/start-course-tools.sh bootstrap
```

From your workstation, open tunnels using the tools VM IP and your private key:

```bash
ssh -i PATH_TO_PRIVATE_KEY -N -L 9000:127.0.0.1:9000 -L 8081:127.0.0.1:8081 azureuser@TOOLS_PUBLIC_IP
```

Open SonarQube on `http://localhost:9000`, change the initial admin password,
require authentication, create the `student-management` project, configure its
quality gate and generate a project analysis token. In Nexus on
`http://localhost:8081`, complete onboarding, change the initial admin password,
disable anonymous access, create a hosted `maven-snapshots` repository if absent,
and create a deployment user restricted to this repository. Obtain Nexus's initial
password only in your private terminal with `sudo docker compose -f
/opt/student-tools/compose.yml exec nexus cat /nexus-data/admin.password`; never
include that screen in evidence. Complete any version-specific onboarding prompts.

After passwords and permissions are configured, on the tools VM:

```bash
sudo bash scripts/start-course-tools.sh https YOUR_TOOLS_FQDN
```

Verify both HTTPS pages and certificate validation. SonarQube on this configuration
analyses the main branch; the Semgrep commit checks cover PRs without needing paid
Sonar branch analysis. Back up PostgreSQL, Nexus volumes and Caddy data off the VM;
Compose volumes survive container replacement, not VM/disk loss.

## GitHub cloud identity and settings

The application VM receives AcrPull automatically. On your authenticated Azure
session, run `scripts/configure-azure-oidc.ps1` with PowerShell after applying the
coursework workspace. It creates/reuses the Entra application, GitHub federated
identity, registry-scoped AcrPush/Reader and VM-scoped Run Command access. Its output
lists the required identifiers. The script supports Windows and Linux Cloud Shell.
Run Command is root-equivalent on that one VM; do not use subscription Contributor.

Set these **environment variables** in GitHub environment `azure-lab`:

| Variable | Value |
| --- | --- |
| AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID | OIDC script output |
| AZURE_RESOURCE_GROUP, ACR_NAME | Terraform / OIDC script output |
| COMPOSE_VM_NAME | Terraform vm_name output |
| SONAR_HOST_URL | `https://YOUR_TOOLS_FQDN` |
| SONAR_PROJECT_KEY | `student-management` |
| NEXUS_MAVEN_URL | `https://YOUR_TOOLS_FQDN:8443/repository/maven-snapshots/` |
| SMTP_HOST, SMTP_PORT | Provider SMTP server; STARTTLS port, normally 587 |
| MAIL_FROM, MAIL_TO | Your verified sender and intended recipient address |

Set these **environment secrets**, never paste their values into chat or Git:
`SONAR_TOKEN`, `NEXUS_USERNAME`, `NEXUS_PASSWORD`, `SMTP_USERNAME`, `SMTP_PASSWORD`.

Set repository variable `EMAIL_ENABLED=true` only after the SMTP configuration and
recipient are ready. Keep repository variable `AZURE_DEPLOY_ENABLED=false` so the
earlier k3s workflow cannot deploy to the Compose VM. Merge the reviewed PR before
dispatching **Coursework - SonarQube Nexus Compose** on master.

For monitoring, tunnel app VM ports 8089, 9091 and 3000 to the same local ports.
Grafana's generated password is stored in `/opt/student-course/.env` on that VM;
do not print it in CI or screenshots. The dashboard is provisioned automatically.
The health check verifies live scraping; visually inspect the dashboard under API
traffic before claiming demonstrated graphs. Pipeline email is separate from metric
alerting: Alertmanager/email alerts from Prometheus are not configured here.

## Evidence and deliberate failure exercises

Use [EVIDENCE-CAPTURE.md](EVIDENCE-CAPTURE.md). Do not leave bugs or vulnerable
dependencies in the delivery branch just to obtain a red screenshot. Existing
historical failures are real; exercises are clearly labelled simulations.

## References used for this implementation

- [pre-commit installation and local hooks](https://pre-commit.com/)
- [Semgrep in CI](https://semgrep.dev/docs/semgrep-ci/sample-ci-configs)
- [Trivy filesystem scanning](https://trivy.dev/latest/docs/target/filesystem/)
- [SonarQube blocking quality gate](https://docs.sonarsource.com/sonarqube-server/10.0/analyzing-source-code/ci-integration/overview)
- [Maven deployment credentials](https://maven.apache.org/guides/mini/guide-deployment-security-settings.html)
- [Dependabot configuration](https://docs.github.com/en/code-security/dependabot/working-with-dependabot/dependabot-options-reference)
- [SonarQube Linux host requirements](https://docs.sonarsource.com/sonarqube-server/2026.1/server-installation/pre-installation/linux)
- [Caddy ACME challenge configuration](https://caddyserver.com/docs/caddyfile/directives/tls)
