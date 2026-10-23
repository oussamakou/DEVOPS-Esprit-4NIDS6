# Student API threat model

Owner: Oussama Koudhai. Scope: this learning lab, synthetic student data only.
Review this document when API entry points, secrets, dependencies, CI permissions,
deployment topology or exposed ports change. A hook checks syntax/secrets; it cannot
replace a human threat-model review.

## Data flow and trust boundaries

Developer -> Git staged snapshot -> GitHub repository -> hosted Actions runner
-> SonarQube / Nexus over HTTPS -> scanned image -> Azure Container Registry
-> Azure VM managed identity -> Docker Compose app -> private MySQL network.
Prometheus scrapes the private management port; Grafana reads Prometheus.
The app, Prometheus and Grafana also join a host-access bridge for Docker's
localhost-only port publishing; this permits outbound traffic. MySQL joins only
the internal database network. Application/monitoring UIs require the SSH tunnel.
An SMTP server receives pipeline status and a run link, never credentials/reports.

The developer workstation, untrusted pull request, trusted delivery environment,
public tool endpoints and private runtime network are separate trust boundaries.
The k3s workflow remains an independent earlier deployment option.

| STRIDE threat | Concrete scenario | Control / evidence | Residual issue |
| --- | --- | --- | --- |
| Spoofing | Anonymous caller impersonates a student/admin | Restrict cloud inbound access to the owner; synthetic records only | API authentication is still absent; unsuitable for public personal data |
| Tampering | PR changes deployment commands or image | Read-only PR jobs; delivery on master with environment protection; image scan and digest deployment | Owner must configure environment branch rules and required reviews |
| Repudiation | No record of who changed a release | Git SHA, Actions logs, Nexus coordinates, scan artifacts and run URL | Artifact retention is finite; save selected evidence |
| Information disclosure | A token enters Git or a log | Staged and history Gitleaks; environment secrets; redacted reports; no shell tracing | Rotate any real leaked secret; deleting a file is insufficient |
| Denial of service | Heavy requests exhaust the lab VM | Resource limits, readiness checks, Prometheus target check | No authentication/rate limiter or multi-node resilience yet |
| Elevation of privilege | User input reaches SQL or shell | Semgrep rules, Sonar quality gate, parameterized JPA usage review | The checked-in Semgrep rules cover selected patterns, not every vulnerability |
| Tampering / over-posting | Client JSON is bound directly to a persistent entity and can influence fields or associations | First live Sonar analysis reported six HIGH `java:S4684` findings; preserve the baseline and introduce explicit request DTOs | DTO remediation is still open; the first baseline's passed new-code gate is not proof of overall security |
| Supply chain | A vulnerable dependency reaches the JAR/image | Trivy JAR and image gates; Dependabot update PRs; pinned actions | Review transitive versions, new CVEs and supporting service images |
| Secrets / infrastructure | Build identity compromises the subscription | OIDC, registry-scoped push/read, VM-scoped Run Command; VM AcrPull | Run Command is root-equivalent on that VM |
| Persistence | VM/disk loss destroys Nexus or student data | Persistent Compose volumes and backup/restore procedure | A volume is not an off-VM backup; restore drill remains required |

## Review checklist

- Identify changed entry points, assets, data flows and trust boundaries.
- Record a concrete abuse case, owner, mitigation and remaining risk.
- Link the failing check, remediation commit and passing rescan.
- Revisit accepted risks before exposing a service or using real records.

## Open work

API authentication/authorization, request validation, TLS for API access, rate limiting,
off-VM backups and tested restoration remain explicit engineering work. Do not invent
additional defects for screenshots. Use the labelled security exercises and actual
historical failures linked in SECURITY-GATE-CASE-STUDY.md.
The [first live Sonar baseline](SONAR-FIRST-BASELINE.md) records six existing HIGH
entity-binding findings, five MEDIUM reliability impacts and 41.5% overall coverage.
