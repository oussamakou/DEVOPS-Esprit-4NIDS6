# Acceptance phase with Nmap

The coursework delivery order is now:

**Pre-commit hooks / threat model → commit security gates → Maven tests/build →
SonarQube → Nexus → image build/scan → ACR → Compose deployment → Nmap acceptance
→ monitoring verification → email.**

Nmap tests a running environment, so it follows deployment. The existing
pre-commit, Semgrep, secrets, dependency and infrastructure checks still run
before Maven compilation. Nmap is a network exposure acceptance test; it does not
replace SAST, dependency scanning or API authorization testing.

## What the gate accepts

Only the owned `studentcourse` lab targets in `security/nmap-policy.json` are
scanned. The TCP scope is ports 1–1024 plus 2375, 2376, 3000, 3306, 5432, 6443,
8080, 8081, 8089, 8443, 9000, 9090, 9091, 9100, 10250 and 30089. UDP and other
TCP ports are outside this acceptance test. Scans use TCP connect (`-sT`), no DNS
lookups (`-n`), no host-discovery dependency (`-Pn`), light service detection
(`-sV --version-light`), bounded rate/retries and a per-host timeout. No exploit
or vulnerability NSE scripts run.

| Scanner viewpoint | Target | Required and allowed open TCP ports |
| --- | --- | --- |
| External GitHub runner | App public IP `158.158.49.102` | None in the tested scope |
| External GitHub runner | Tools public IP `68.221.67.223` | 443, 8443 (SonarQube/Nexus HTTPS) |
| Application VM | `127.0.0.1` on the application VM | 22, 3000, 8089, 9091 |
| Application VM | App private IP `10.42.1.4` | 22, 9100 |
| Application VM | Tools private IP `10.42.2.4` | 22, 443, 8443, 9100 |

SSH is restricted to the owner's public IP, so it must not be open to the
external GitHub runner. Running the external policy from the owner's PC changes
the viewpoint and can legitimately fail this expectation. The internal scan must
run on `studentcourse-vm`; the script rejects a different scanner hostname.
Check ownership and update the tracked policy if Azure resources/IPs change.

Examples of real acceptance failures: externally open MySQL 3306, externally open
Node Exporter 9100, or a missing private exporter. Closed and filtered are recorded
distinctly. Filtered means the scanner received no usable response; it is not
proof that the underlying host has no service. `-Pn` assumes a target is up.
Required internal/HTTPS services provide positive controls for the combined gate.

The gate rejects unexpected open ports, missing required ports, failed/timed-out
scans, wrong targets, incomplete port coverage, missing XML/text/version reports
and policy mismatches. The final collector rechecks the original XML, rather
than trusting a green result JSON alone. Report transport is checksummed and
chunked to avoid Azure Run Command's output limit. All original files are returned
to the runner; a fresh report archive also remains under
`/opt/student-course/acceptance/nmap/` on the application VM.

## Run against the existing deployment

After this change is merged, run **Acceptance - Nmap Azure network policy** on
`master` from GitHub Actions, or from the authenticated repository CLI:

```powershell
gh workflow run acceptance-nmap.yml --ref master
gh run list --workflow acceptance-nmap.yml --limit 3
```

This validates the existing deployed environment without rebuilding the
application. The full **Coursework - SonarQube Nexus Compose** workflow calls the
same acceptance workflow after deploying its new image. Acceptance failure blocks
the later monitoring job, and the email reports the pipeline failure. It does not
automatically roll back the deployed release.

The external scan runs on an Ubuntu GitHub runner. The private/loopback scan runs
through the existing Azure managed identity's app-VM Run Command permission.
No SSH firewall expansion, new VM, public monitoring port or Azure role grant is
required. Nmap is installed from Ubuntu's package repository, and its actual
version is saved in each viewpoint's reports.

## Original reports for the professor

Download artifact **nmap-acceptance-original-reports**, extract it and open
`index.html`. The folder is self-contained and usable without GitHub. It includes
the original `.xml`, `.nmap`, `.gnmap` and console `.log` for each scan, plus
version records and the acceptance summary. For an already known run ID:

```powershell
gh run download RUN_ID --name nmap-acceptance-original-reports --dir .tools/nmap-acceptance-evidence
```

Demonstrate the acceptance summary, then open an original `.nmap` file and explain
the target, scanner viewpoint, open ports, filtered ports and service observations.
Show that Java/database/exporter ports stay off the public endpoints. Nmap service
identification does not establish a CVE finding or prove a service is patched.

For parser/gate regression tests: `python scripts/test-nmap-acceptance.py`.
Those tests use temporary, explicitly controlled XML fixtures and perform no
network scans. They are not live vulnerability evidence. Preserve actual scan
failures if they occur; do not weaken the production NSG or expose a database to
manufacture a screenshot.

References: [TCP scanning](https://nmap.org/book/man-port-scanning-techniques.html),
[XML output](https://nmap.org/book/output-formats-xml-output.html),
[port states](https://nmap.org/book/man-port-scanning-basics.html).
