# A real blocked build: dependency and base-image findings

This records actual workflow evidence, not a simulated CV incident. The first
completed image scan on commit `363a2a9` failed the HIGH/CRITICAL policy:

[Failing run and scan artifacts](https://github.com/oussamakou/DEVOPS-Esprit-4NIDS6/actions/runs/39510045211)

The runtime image used an up-to-date 17-JRE Alpine tag at build time and the app used
Spring Boot 3.5.16. Despite that, the scan reported:

| Component | Installed | Reported fixed version / action |
| --- | --- | --- |
| libexpat | 2.8.5-r0 | 2.9.0-r0; upgrade runtime OS packages when rebuilding |
| jackson-core/databind | 2.21.4 | 2.21.7 or newer; move to the newer Boot/Jackson stack and manage any remaining Jackson 2 dependency |
| tomcat-embed-core | 10.1.55 | 10.1.58 or 11.0.25; use Boot 4 with Tomcat 11.0.25 override |
| spring-webmvc | 6.2.19 | Scan identified 7.0.9; migrate to Boot 4.1.1's supported Framework 7 stack |

The report contained 11 HIGH/CRITICAL findings across these packages. The complete
report is authoritative for CVE IDs, package paths and severity attribution. Review
the linked vendor advisory for a specific vulnerability before discussing exploitability.

The response was to keep `--exit-code 1`, upgrade the runtime packages and application
dependencies, and adapt the application tests to Boot 4's modular testing/metrics
configuration. A multi-stage build was already present, and would not remove vulnerable
libraries packaged in the JAR. Using a JRE instead of a JDK also would not fix them.

The fix must be confirmed by a new scan of the rebuilt image and functional tests.
Until that scan passes, this is a **blocked build being remediated**, not a cleared release.
No Azure production release was attempted or claimed. The CVE database may change later,
so a pass on one day is not a permanent vulnerability-free guarantee.

The next scan on Boot 4.1.1 cleared the original OS/Framework/Tomcat findings but
still blocked five HIGH findings in Jackson 3.1.5, the version managed by Boot's
BOM. The response was an explicit Jackson 3 BOM override to 3.1.7, the patched line
listed in the report. Updating a framework version alone is not proof that every
transitive dependency is patched. The same run passed the disposable k3s test,
including an actual write/read, MySQL pod replacement, persistence and Prometheus UP.

[Intermediate failing rescan and successful k3s test](https://github.com/oussamakou/DEVOPS-Esprit-4NIDS6/actions/runs/39511097031)

## Interview explanation

**Verified outcome:** [run 39512642589](https://github.com/oussamakou/DEVOPS-Esprit-4NIDS6/actions/runs/39512642589)
passed Maven, Gitleaks, Terraform/Checkov, the image build and ephemeral k3s test,
and the full-image Trivy gate with **zero HIGH/CRITICAL findings**. Azure deployment
was intentionally skipped: the account/identity setup is still an owner action.
The passing scan applies to that image and vulnerability database snapshot, not to
all future image tags or every supporting infrastructure image.

Explain the trigger, failed gate, affected package, selected upgrade, tests, rescan
result and remaining risk. Do not claim a scan failed in production when it failed
before publication. Do not attribute this fix to adding multi-stage Docker: that was
already in the original project.
