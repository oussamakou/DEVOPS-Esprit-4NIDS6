# Validation record

This file distinguishes local verification from cloud results. It must not be read
as proof of an Azure deployment. The cloud account and billing setup remain owner steps.

## Baseline

The original application at `2a9c8e5` built successfully on Java 17 and Maven 3.9.9
with three tests passing. It already used a multi-stage Dockerfile.

## Extension checks

The following are updated after the local implementation checks finish:

- Maven build and HTTP/management tests: pending final run.
- Terraform init/validate: passed locally, without applying Azure resources.
- Terraform provider lock includes Linux and Windows x86_64 checksums.
- Python/YAML/dashboard structure and deploy bundle generation: passed initial structural check.
- Gitleaks available Git history/current tree: passed with the exact historical
  classroom Secret fingerprint documented in SECURITY.md.
- Checkov: 23 enabled checks passed, zero failures/parsing errors, with 10 explicit
  lab policy exclusions documented in SECURITY.md. The isolated internet-wide SSH
  rejection demonstration is checked separately.
- GitHub workflow syntax/action lint and Linux shell syntax: pending final check.
- Docker Desktop: engine restored by preserving/renaming its runtime socket
  directories, with settings backed up. No container/volume/data disk was deleted.
  Local image build initially hit a Docker Hub TLS handshake timeout. Image scan
  and Compose runtime validation depend on a completed image pull/build.
- GitHub hosted workflow / Azure apply / k3s runtime / dashboard scrape and rollback:
  not yet verified in a cloud account.

The tool installer verifies SHA256 manifests fetched from each tool's release host.
This detects corrupt/mismatched downloads; it is not independent verification of
the publisher's signing identity. GitHub Actions are resolved to immutable commits.
Review automated update PRs rather than assuming pinned software stays safe forever.
