# Capture real failures and their fixes

## Actual Nexus default secret-encryption key finding

After tools onboarding, Nexus's status screen reported an unhealthy check:

```text
Nexus was not configured with an encryption key and is using the Default key.
```

This is a genuine deployed service-configuration finding, separate from application
code vulnerabilities and the labelled negative fixtures. The original bootstrap
had changed admin passwords but had not configured a private encryption key.

![Before: Nexus reports the default encryption key](screenshots/nexus_default_encryption_key_before.png)

The remediation generates a private 32-byte key once on the tools host, exposes
its JSON configuration to Nexus through a read-only bind mount and
`NEXUS_SECRETS_KEY_FILE`, and preserves the key across bootstrap reruns. Its mode is
400 with Nexus UID/GID 200 ownership. The authenticated secrets re-encryption API
accepted the request (HTTP 202); the task log reported `RUNNING -> OK`.
An immediate-completion task disappeared from the task-list API, so that polling
result alone was not treated as successful completion. The task log and live health
screen confirmed the result. No key value appears in the screenshots or Git.

![After: Nexus uses the private coursework-v1 key](screenshots/nexus_private_encryption_key_after.png)

A live bootstrap rerun preserved the key's checksum. Both public HTTPS endpoints
still accepted their limited CI credentials, while anonymous requests were rejected
with HTTP 401. Keep a private backup of the key together with Nexus data backups.
See [Sonatype's re-encryption guide](https://help.sonatype.com/en/re-encryption-in-nexus-repository.html).

## Service setup verification before the first delivery

![Private SonarQube project ready for its first analysis](screenshots/sonarqube_private_project_ready.png)

The project exists, its main branch is `master`, and a project-limited CI analysis
token has been validated. The screenshot correctly shows that the main branch has
not yet been analyzed. It is setup evidence, not a passing quality gate or deployment.

## Actual Azure directory-permission failure

After the 19-resource apply and successful tools-container bootstrap, the original
OIDC setup attempted to create an Entra app registration and failed:

```text
ERROR: Directory permission is needed for the current user to register the application.
Original error: Insufficient privileges to complete the operation.
```

Capture the Cloud Shell command, error and returned prompt. Azure subscription
resource permissions do not automatically grant app-registration permissions in
the tenant. The remediation changes the script to a user-assigned managed identity
with GitHub federation, using Azure resource permissions and no Graph lookups.
It retains registry-scoped push/read and single-VM Run Command assignments.
Seven offline scenarios check trust, scopes, reruns and failure handling. Capture
the successful identity setup and a real OIDC login only after they actually run;
offline checks alone do not establish a successful cloud sign-in.

## Actual Azure subscription eligibility failure

Cloud Shell reached phase `[3/7]` and Azure reported:

```text
Standard_B2s is restricted in francecentral: NotAvailableForSubscription
Preparation stopped at line 25 (exit 1). No apply command was run.
```

This is an actual subscription/SKU restriction encountered during preparation,
not an application vulnerability or a failed resource deployment. Save a screenshot
of that terminal output with the phase and error visible. The preparation gate
blocked before Terraform inputs and resource creation. The follow-up is to discover
eligible SKU alternatives, verify their family/regional quota and memory, then
generate and review a new plan.

The follow-up discovery in policy-allowed Spain Central also rejected B2s, while
accepting `Standard_B2als_v2` (2 vCPU / 4 GiB) and `Standard_D4s_v4` (4 vCPU /
16 GiB). The owner's quota output showed 0/6 regional, 0/10 Basv2 and 0/4 DSv4
vCPUs used. Capture those eligible rows and quota limits as the verified selection
after the error. The coursework defaults now use that pair. This resolves the
size-selection issue; it is not evidence of successful VM allocation or deployment.

Keep the run URL, Git SHA, failing step, redacted report, explanation, remediation
commit and passing rescan together. Include date/tool version, and capture enough
of the page to identify the run. Hide credentials, private student records and
initial admin passwords. Screenshot images are manual evidence until actually
captured; logs and configuration alone are not screenshots.

## Genuine existing application failures

The [first blocking Trivy run](https://github.com/oussamakou/DEVOPS-Esprit-4NIDS6/actions/runs/39510045211)
and [intermediate Jackson rescan](https://github.com/oussamakou/DEVOPS-Esprit-4NIDS6/actions/runs/39511097031)
are real dependency/base-image failures. Open the failing scan step and screenshot
the finding and red status. Use [the passing rescan](https://github.com/oussamakou/DEVOPS-Esprit-4NIDS6/actions/runs/39512642589)
for the after screenshot. The [case study](SECURITY-GATE-CASE-STUDY.md) explains the
actual versions and fixes. Download artifacts before they expire; older logs or
artifacts may no longer be available.

## Repeatable labelled exercises

In Actions, choose **Security exercise - intentional failure**, Run workflow and
select `hook`, `secret` or `sast`. This workflow has no deployment steps. A temporary
directory contains either malformed YAML, a deliberately fake token or a small Java
command-execution fixture. A real scanner rejects it; exit code 1 makes the job red.
Tool crashes/missing findings instead report EXERCISE_INVALID, which is not a
successful security demonstration. Fixtures are discarded automatically.

Screenshot the step **Reject the temporary fixture (expected red job)** with the
`CONTROLLED EXERCISE` label and the finding. Download `labelled-exercise-evidence`.
Then run the regular commit-security workflow on clean application code and capture
its passing hook/SAST/dependency checks separately. Do not present an exercise as
an organically discovered application vulnerability, or hide the exercise label.

Locally (using the hooks Python environment):

```powershell
.tools/hooks-venv/Scripts/python.exe scripts/security-exercise.py hook
.tools/hooks-venv/Scripts/python.exe scripts/security-exercise.py secret
```

These two commands were actually verified to reject their intended fixtures during
implementation. Semgrep runs in Linux CI. The exercise returns nonzero on purpose;
do not add continue-on-error to the delivery gates.

## Actual hook integration failure

During implementation the first full file-hook run failed with a UnicodeDecodeError
on `documentation/LEGACY-JENKINS-MINIKUBE.md`, an existing UTF-16 document. The fix
detects its byte-order marker and scans the decoded contents. A regression check
confirms both that valid UTF-16 passes and that a merge marker in UTF-16 is rejected.
This was a hook compatibility failure, not a discovered application vulnerability.

## Actual coursework infrastructure finding

The first enabled-tools Checkov scan rejected `tools_https` under CKV_AZURE_160:
the NSG allowed public HTTP port 80 for certificate validation. The scan reported
42 passing checks and one failure. Commit `83c5161` preserves this original
configuration and a CI check that scans the optional tools resources explicitly;
the default configuration alone would not test resources whose count was zero.
No resources were applied from that revision. The correction closes port 80 and
configures Caddy to use TLS-ALPN certificate validation on 443. The policy remains
enabled; no ignore/soft-fail exception is added. Capture the red infrastructure
step and the later passing rescan, and explain this network-exposure finding.

[Actual failed infrastructure job](https://github.com/oussamakou/DEVOPS-Esprit-4NIDS6/actions/runs/39805052147/job/119915917317).
The [saved screenshot](screenshots/coursework_checkov_failed.png) shows that the
optional-tools gate failed while earlier checks passed; expand the failed step
while signed in to see the detailed CKV_AZURE_160 finding.

[Passing rescan job](https://github.com/oussamakou/DEVOPS-Esprit-4NIDS6/actions/runs/39805591559/job/119917830983)
and [saved passing screenshot](screenshots/coursework_checkov_passed.png) confirm
that the enabled-tools policy scan and Compose/Caddy validation subsequently passed.

## Cloud screenshots after provisioning

| Screenshot | What it proves |
| --- | --- |
| Actions checkout/Maven logs plus SHA | Exact revision compiled and tested |
| SonarQube finding and failed/passing quality gate | Actual analysis and gate decision |
| Nexus Maven coordinates and timestamp | Tested JAR uploaded to Nexus |
| ACR repository digest | Immutable scanned image published |
| Compose stage and success marker | Digest started on the Azure VM and API/database check passed |
| Prometheus target UP and Grafana charts | Live metrics under real test traffic |
| Received status email with Actions link | SMTP delivery reached the intended inbox |

A configured step or an SMTP acceptance message alone does not prove an email
arrived. A skipped Azure/Sonar/Nexus step is not a passing deployment screenshot.
