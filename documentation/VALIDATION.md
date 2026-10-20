# Validation record

This file distinguishes local verification from cloud results. It must not be read
as proof of an Azure deployment. The cloud account and billing setup remain owner steps.

## Baseline

The original application at `2a9c8e5` built successfully on Java 17 and Maven 3.9.9
with three tests passing. It already used a multi-stage Dockerfile.

## Extension checks

The following are updated after the local implementation checks finish:

- Maven build: passed with 6 tests on Boot 4.1.1, including actual HTTP create/read/delete,
  health probes, Prometheus export and management/application port separation.
- Terraform init/validate: passed locally, without applying Azure resources.
- Terraform provider lock includes Linux and Windows x86_64 checksums.
- Python/YAML/dashboard structure and deploy bundle generation: passed initial structural check.
- Gitleaks available Git history/current tree: passed with the exact historical
  classroom Secret fingerprint documented in SECURITY.md.
- Checkov: 26 enabled checks passed, zero failures/parsing errors, with 10 explicit
  lab policy exclusions documented in SECURITY.md. The isolated internet-wide SSH
  rejection demonstration passed for CKV_LAB_1 on a temporary literal /0 fixture.
- Workflow actionlint and Linux shell syntax: passed. Hosted CI also runs workflow
  lint, the negative SSH test and supporting-file structural checks.
- Docker Desktop: engine restored by preserving/renaming its runtime socket
  directories, with settings backed up. No container/volume/data disk was deleted.
  Local image build passed after retrying a Docker Hub TLS timeout. The engine later
  became unavailable again, so local Trivy/Compose runtime checks were not completed.
- Hosted ephemeral k3s: passed the API write/read, MySQL pod replacement/PVC persistence,
  workload readiness, monitoring deployment and Prometheus target-UP checks in
  [run 39511097031](https://github.com/oussamakou/DEVOPS-Esprit-4NIDS6/actions/runs/39511097031).
- Azure apply, managed identity/OIDC deployment, off-VM backup restore and rollback
  remain unverified in a cloud account.

Hosted Maven, Gitleaks and Terraform/Checkov stages have passed. The first application
Trivy scan blocked 11 HIGH/CRITICAL findings. See `SECURITY-GATE-CASE-STUDY.md` for the
actual report and remediation, rather than treating that failed run as a completed release.

The GitHub `azure-lab` environment was prepared with a master-only deployment branch
policy and `AZURE_DEPLOY_ENABLED=false` at repository scope. No Azure account,
cloud resource or deployment credential was created by that preparation.

The tool installer verifies SHA256 manifests fetched from each tool's release host.
This detects corrupt/mismatched downloads; it is not independent verification of
the publisher's signing identity. GitHub Actions are resolved to immutable commits.
Review automated update PRs rather than assuming pinned software stays safe forever.
