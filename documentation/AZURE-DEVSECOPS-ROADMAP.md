# From the existing student API to Azure DevSecOps

This is a learning and implementation roadmap, not a record of an Azure deployment.
The starting point is commit `2a9c8e5` of `oussamakou/DEVOPS-Esprit-4NIDS6`.

**Update:** the local implementation now includes the Azure configuration, security
pipeline, hardened workloads, monitoring and study guide. The inventory below
describes the original baseline. See `START-HERE.md` and `VALIDATION.md` for the
current implementation and what has actually been verified.

## What we can reuse

| Existing piece | What it does | How it fits the Azure project |
| --- | --- | --- |
| Spring Boot API | Handles students, departments and enrollments | Keep the application; infrastructure is the focus |
| Maven and tests | Compile Java, resolve dependencies and check behavior | First GitHub Actions stage |
| Dockerfile | Builds the JAR in one stage and runs it in a JRE stage | Improve caching and permissions, then scan the final image |
| Kubernetes manifests | Describe application and MySQL workloads and services | Adapt to k3s and add probes, resources and storage |
| Jenkinsfile | Automates the existing local workflow | Keep as the earlier approach; implement the Azure path with GitHub Actions |
| Existing reports | Explain the original school project | Preserve provenance and add a separate account of the Azure extension |

The repository does not currently contain Terraform, GitHub Actions workflows,
Gitleaks/Checkov/Trivy gates, or Prometheus/Grafana configuration. The application
does not yet include the Actuator and Prometheus dependencies.

## Learn and build in this order

### 1. Understand and run the existing application

From the repository root in PowerShell:

```powershell
.\mvnw.cmd -B verify
```

Java 17 is required by this project. Maven downloads dependencies on its first run.
The tests select the `test` Spring profile and use an H2 in-memory database.
The normal application uses MySQL; a successful test run alone does not prove
that the MySQL connection or container deployment works.

Trace a request through these files:

1. `controllers/StudentController.java`: maps an HTTP request to a Java method.
2. `services/StudentService.java`: coordinates the operation.
3. `repositories/StudentRepository.java`: Spring Data provides database operations.
4. `entities/Student.java`: maps a Java object to a database table.

These paths are relative to `src/main/java/tn/esprit/studentmanagement/`.
For example, `GET /student/students/getAllStudents` reaches the controller,
calls the service, queries the repository, and returns students as JSON.
The `/student` prefix comes from `server.servlet.context-path`.

Explain aloud: Why can tests run without MySQL? What does the repository layer do?
What is the difference between a test passing and a deployed service being healthy?

### 2. Make the local containers dependable

Start Docker Desktop before trying `docker compose` commands. The Docker client
can be installed while the Docker engine is stopped.

Before using this application on Azure:

- Remove database passwords from tracked configuration and supply them at runtime.
- Give the application a dedicated MySQL user instead of database root access.
- Add a database health check and handle application startup before MySQL is ready.
- Add a `.dockerignore`, run the application as a non-root user, and retain the
  existing multi-stage build.
- Update dependencies as needed and scan the resulting image. A small image can
  still contain vulnerable OS packages and vulnerable Java dependencies.

Explain aloud: What is an image versus a container? Why does the runtime image
not need Maven? Why does `depends_on` alone not guarantee database readiness?

### 3. Build the security pipeline without cloud credentials

Implement six logical stages:

1. Maven build and tests.
2. Gitleaks secret scan.
3. Checkov Terraform scan, once Terraform exists.
4. Docker build with layer caching.
5. Trivy image scan, failing for HIGH and CRITICAL vulnerabilities, including
   unfixed findings unless an explicit, documented exception is approved.
6. Deploy only after all required stages pass, and only from the trusted branch.

Secret leaks and infrastructure policy violations do not all share Trivy's
severity model. Define each gate's failure policy explicitly. Until Terraform
exists, show its stage as pending work rather than claiming infrastructure passed.

Build once, scan that image, and deploy that same image using an immutable digest.
Keep cloud credentials unavailable to untrusted pull request code. Prefer Azure
OIDC federation over a stored client secret. Preserve reports for interview evidence.

Explain aloud: How is secret scanning different from vulnerability scanning?
Why must the scanned image be the deployed image? What stops a failed gate from deploying?

### 4. Create the Azure infrastructure with Terraform

Create the Azure subscription first. Check actual regional prices, credit terms,
VM quotas and a budget before provisioning. A VM, disks, public IP and container
registry are not guaranteed to be free. Stopping a guest OS does not necessarily
stop compute billing; deallocation still leaves other billable resources.

Use Terraform for a resource group, virtual network, subnet, network security
group, Linux VM and Azure Container Registry. Keep SSH restricted to your own
public IPv4 `/32`, authenticate using an SSH key, and keep the Kubernetes API
private. Plan how CI will reach the deployment before choosing network rules;
GitHub-hosted runners cannot reach a private API automatically.

Keep Terraform state and variable files containing private information out of
Git. Use a secure remote backend for shared or automated infrastructure changes.
Run formatting, validation, Checkov and a reviewed plan before the first apply.

Explain aloud: What is desired state? What is in Terraform state? What is the
difference between a subnet and a network security group? Why is SSH `/32` safer?

### 5. Deploy to k3s with a working database

k3s is a Kubernetes distribution. Use the existing application as the workload.
Add startup/readiness/liveness probes, CPU and memory settings, an image pull
authentication mechanism, and persistent storage for MySQL. A Kubernetes Secret
is not protected merely because its values are base64 encoded.

The current MySQL deployment has no persistent volume. Replacing its pod can
lose data. A single VM with local persistent storage is still vulnerable to VM
or disk loss; demonstrate backup and restore, and describe that limitation.

Check rollout completion and a real API request after deployment. Practice
rollback to a known digest. An application rollback does not undo database changes.
Use synthetic students only while the API has no authentication or HTTPS.

Explain aloud: What does a Deployment do? How does a Service find pods? Why are
readiness and liveness different? Why is one VM not highly available?

### 6. Monitor and collect honest measurements

Add Spring Boot Actuator and Micrometer's Prometheus registry. Configure Prometheus
to scrape metrics and Grafana to display request rates, errors, latency, JVM heap
and process health. Keep management dashboards and metrics access restricted.
Account for the application's `/student` context path when configuring probes and scraping.

Measure several cold-cache and warm-cache pipeline runs. Record commit, workflow
run URL, stage durations, cache status, runner type and deployed digest. Compare
the same start and end events; exclude one-time infrastructure provisioning from
application deployment timing and state that choice.

Measure image size with the same tool and definition for both versions. Separate
compressed registry size from local image size. Keep the actual scanner output
and dependency or base image changes that resolve findings.

Explain aloud: What does caching save? What invalidates a Docker layer? What does
Prometheus store, and what does Grafana do? What evidence supports the speed claim?

## Interview story to build toward

Explain the real sequence: an existing school project using Jenkins and Minikube
was extended with Azure provisioning, GitHub Actions, security gates and monitoring.
Describe your personal contribution precisely.

Do not yet claim that Azure is deployed, a release was blocked by Trivy, SSH was
flagged by Checkov, image size fell from 480 MB to 190 MB, or deployment time fell
from 14 to 5 minutes. Those are hypotheses or targets until backed by actual runs.
The Dockerfile already uses a multi-stage build, so that technique alone cannot
be presented as a newly implemented improvement to this baseline.

## References

- [GitHub OIDC with Azure](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure)
- [k3s quick start](https://docs.k3s.io/quick-start)
- [k3s private registry configuration](https://docs.k3s.io/installation/private-registry)
- [Azure Container Registry authentication](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-authentication)
- [Checkov command reference](https://www.checkov.io/2.Basics/CLI%20Command%20Reference.html)
