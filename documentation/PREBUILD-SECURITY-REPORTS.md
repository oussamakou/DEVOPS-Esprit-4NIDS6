# Security checks before Maven: reports for assessment

The professor requested the pre-commit/commit techniques before Maven compilation,
with downloadable reports and screenshots. Both workflow entry points now use the
same reusable pre-build security workflow.

## Execution order

1. Checkout source and replay installed pre-commit hook checks.
2. In parallel, run Semgrep, full-history Gitleaks, Terraform/Checkov and source-POM
   dependency analysis. Each waits for the hook job to pass.
   The dependency job first runs `dependency:resolve` to populate Maven's metadata
   cache, without compilation/tests/packaging, then scans the source POM using that
   local metadata. It asserts that no application classes or JAR were built.
3. Collect the actual scanner reports and a readable index.
4. Only after the reusable security workflow succeeds, start Maven compilation,
   tests and packaging. Later delivery stages retain their existing order.

Threat modeling is a manual STRIDE review represented by the saved threat-model
document. CI verifies the document exists and preserves it as evidence; CI does
not claim to automate human threat analysis.

## Artifacts

Open the run's **Artifacts** section and download **professor-security-reports**.
Extract it before opening `index.html`, so its links to the raw files work.

| Technique/check | Evidence in the extracted report |
| --- | --- |
| Threat modeling | `precommit/THREAT-MODEL.md` |
| Pre-commit hooks | `precommit/precommit.log`, `precommit/precommit-result.json` |
| Commit SAST | `sast/semgrep.json`, its log and command outcome |
| Full-history secrets | `secrets/gitleaks.json` (redacted), its log and outcome |
| Infrastructure policies | `iac/checkov-default.*`, `iac/checkov-course.*`, JSON/JUnit/logs and outcomes |
| Dependency inventory and gate | `dependencies/dependencies.json`, `inventory-summary.json`, `sbom.cdx.json`, source POM and log |

Each command outcome records the actual exit status, UTC timestamps, commit SHA
and run URL. Missing/failed commands never become passing records. Checkov
exceptions remain visible in the raw reports and documented `.checkov.yml`.

The Semgrep controlled exercise is under `sast/controlled-exercise`. It uses a
temporary, labelled command-execution fixture and is distinct from the clean
application scan. Do not present this fixture as an organically discovered bug.

## Dependency inventory correction

The old `trivy fs target` report contained no analyzed packages. A successful exit
was not proof of dependency coverage. The corrected helper scans an isolated copy
of this project's source POM without building the JAR. It rejects an empty scan,
missing expected runtime dependencies and dependencies without versions/package
URLs. It also verifies that the generated SBOM retains the analyzed packages.

The local 29 October validation analyzed 108 packages and generated 109 SBOM
components, with no HIGH/CRITICAL findings at that database snapshot. CI must
produce its own reports for the committed revision. Counts can differ when
dependencies or the scanner database change. POM analysis excludes test/optional
dependencies. The later image scan remains a separate check of packaged libraries
and operating-system packages.

## Screenshots to capture

- The workflow graph with pre-commit and commit checks completing before Maven.
- The hook transcript with real Passed/Failed outcomes.
- Semgrep's actual application result, file count and any findings.
- Checkov's passed/failed/skipped policy counts, plus both default/tools reports.
- Trivy's nonempty package count, SBOM component count and policy result.
- The readable report with its revision and Actions URL.

Original reports are the primary evidence; screenshots illustrate them. Save the
downloaded artifact locally because hosted artifact retention is finite.

Sources: [Trivy Java source-POM support](https://trivy.dev/docs/latest/guide/coverage/language/java/)
and [Trivy JSON-to-SBOM conversion](https://www.trivy.dev/docs/v0.53/guide/configuration/reporting/).
