# Capture real failures and their fixes

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
