# Security model and lab limitations

This is an educational single-node deployment, not a hardened production platform.
Only synthetic student records belong in this unauthenticated HTTP API. Azure NSG
rules restrict SSH and the application NodePort to one owner IPv4 /32. Kubernetes
API, MySQL, Actuator, Prometheus and Grafana have no public service port opened.
For encrypted API access use the SSH tunnel in the setup guide.

## What blocks delivery

- Maven build/test failure.
- Gitleaks finding (redacted reports; full available Git history).
- Terraform validation/formatting or an unexcepted Checkov policy failure.
- Trivy HIGH or CRITICAL OS **or Java dependency** vulnerability in the application
  image, including unfixed findings. No blanket ignore-unfixed and no continue-on-error.
- Failed deployment rollout or API/database smoke check. Azure CLI request success
  alone is insufficient; the guest must emit the final success marker.

The pipeline builds an image tar artifact, checks its SHA256 on scan and deployment,
and publishes that same artifact after scanning. Deployment uses its registry digest.
The Docker build uses the JAR that passed CI tests. Tests are not rerun inside Docker.

## Trust boundaries

Pull requests get read-only repository permissions and no Azure identity. Deployment
is limited to master, the azure-lab environment and an explicit repository enable flag.
The environment must restrict deployment branches to master; otherwise an environment
OIDC subject by itself is not branch isolation. Protect master and require checks.
Some environment protections depend on the GitHub plan/repository visibility.

GitHub exchanges OIDC for temporary Azure tokens; there is no stored client secret.
Its principal has registry AcrPush and a custom role on the single VM allowing read
and Run Command. Run Command is root-equivalent **on that VM**. This is a deliberate
lab simplification, not least-privilege Kubernetes RBAC. Never grant this identity
subscription Contributor/Owner. Terraform is applied manually with the owner's account.

The VM's managed identity has AcrPull only. A root-only systemd timer renews its
Kubernetes registry Secret hourly. If it stops, future pod pulls can fail when the
token expires; check timer health. Application egress is restricted by NetworkPolicy,
including no rule permitting Azure's metadata endpoint. Keep the host patched.

Kubernetes Secrets are base64, not encryption by themselves. k3s is configured with
encryption at rest, while authorized root/cluster administrators can still read them.
Generated MySQL/Grafana credentials are created on the VM once and not printed in CI.
Deleting the MySQL Secret while keeping its data volume does not rotate the database
password: use SQL to rotate credentials and update the Secret in a controlled change.

## SSH policy verification

`checkov_checks/InternetSSH.py` supplements Checkov's built-in SSH rule: the pinned
version's address matcher did not reject a literal `0.0.0.0/0` in our isolated fixture.
The custom CKV_LAB_1 policy handles that CIDR, IPv6 /0, wildcard/service tags and port
ranges. Terraform also restricts the actual owner admin_cidr to one valid IPv4 /32.
`scripts/prove-ssh-gate.py` verifies that the insecure fixture is rejected, without
creating any Azure resource. Keep this negative test when updating scanner versions.

## Narrow historical Gitleaks exception

The original school commit `2477b2221dfc7baf0ae66c1a5fd6f9dc3a873d1f` contains
`k8s/mysql-secret.yaml`, a public classroom example containing literal `root` and
`studentdb`. `.gitleaksignore` contains only its exact finding fingerprint. It does
not allowlist a rule, directory or all historical commits. That file is removed and
new deployments use randomly generated passwords. Treat the old password as public;
rotate it on any older installation still using it. Do not add real credential
findings to the ignore file instead of revoking/rotating their credentials.

## Infrastructure exceptions

The following explicit skip-check entries in `.checkov.yml` were selected after
running the full Terraform scan, not to ignore unknown failures:

| Check | Accepted lab tradeoff and residual risk |
| --- | --- |
| CKV_AZURE_50 | Azure VM agent/extensions are enabled for Run Command; that VM-scoped deployment role is root-equivalent. |
| CKV_AZURE_119 | The VM has a public IP for owner SSH/API access; NSG rules enforce a single owner /32. |
| CKV_AZURE_139 | Basic ACR has a public authenticated endpoint so hosted runners can push; no private endpoint. |
| CKV_AZURE_163 | Paid Defender image scanning is omitted; Trivy blocks HIGH/CRITICAL in the application image before publication. Other images and post-release CVEs remain a separate obligation. |
| CKV_AZURE_164 | Registry content trust/signature enforcement is omitted; digests/checksums provide content identity, not signer provenance. |
| CKV_AZURE_165 | Geo-replication is omitted in this single-region lab; no multi-region recovery guarantee. |
| CKV_AZURE_166 | Registry quarantine workflow is omitted; the application pipeline scans before pushing. Alternate writers would need equivalent controls. |
| CKV_AZURE_167 | Premium retention policy is omitted; owner must remove old images to control storage costs. |
| CKV_AZURE_233 | Zone-redundant registry availability is omitted; single-region registry failure affects image pulls. |
| CKV_AZURE_237 | Dedicated Premium data endpoints are omitted; Basic ACR uses its shared public data endpoint. |

These are policy exclusions, not passing security checks. Review them for any
production use; no general soft-fail or severity blanket hides additional findings.
Every enabled Terraform rule is a blocking gate. A Basic public
ACR endpoint uses authentication; network-private endpoints require a different SKU
and network path for GitHub-hosted runners. Evaluate these cost/security tradeoffs
before calling this architecture production-ready.

## Remaining work before a real production deployment

- API authentication/authorization, HTTPS, input validation, and safe entity/DTO mappings.
- Managed database or tested off-VM backups, schema migrations and restore drills.
- Multiple Kubernetes nodes / control plane resilience; this VM and its local disk
  are single points of failure. A PVC survives pod replacement, not arbitrary VM loss.
- Pinned container digests, signature/attestation verification, action/dependency updates,
  and recurring scans of already running images. CVE databases change after release.
- Scan and maintain MySQL, Prometheus and Grafana images too. The application-image
  gate does not assert that every infrastructure image is vulnerability-free.
- Monitoring data is ephemeral (24h retention/size cap), provisioned dashboards survive
  recreation but historical metrics and interactive dashboard edits do not.
- The Prometheus alert is visible locally; no Alertmanager notifications are configured.
- A new Terraform-managed VM does not restore data from the old VM automatically.
- The k3s installer is fetched over HTTPS at provisioning time, with a pinned k3s
  version. Review/vendor the installer and verify release signatures for stronger provenance.
