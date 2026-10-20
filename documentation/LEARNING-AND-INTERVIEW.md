# Understand the implementation, then explain it

Use this as a study guide. Run the examples and inspect the files instead of
memorizing answers to events you have not experienced. Speak in past tense only
for work you have actually built, tested or deployed.

## 1. What your application does

An API accepts HTTP requests and responds with data. Here the data describes students,
departments and enrollments. Spring Boot starts an embedded web server; Maven compiles
the Java source and packages the app and its dependencies into an executable JAR.

Trace `GET /student/students/getAllStudents`:

1. `application.properties` provides the `/student` context prefix.
2. `StudentController.getAllStudents` maps the remaining URL to a Java method.
3. `StudentService.getAllStudents` coordinates the operation.
4. `StudentRepository` extends Spring Data's repository interface; its implementation
   queries the database through JPA/Hibernate.
5. `Student` maps the Java fields to the database table; Spring serializes results to JSON.

**Interview: Why do you have controller/service/repository layers?**
The controller handles HTTP, the service holds application operations, and the repository
handles persistence. These boundaries let us change and test responsibilities separately.

**Interview: Unit test versus integration test?**
A unit test isolates a small part, usually replacing its dependencies with mocks.
The original `StudentServiceTest` uses `@SpringBootTest` and a real H2 repository, so
it is a Spring/database integration test despite its filename. The added HTTP test
also starts a real embedded server. Neither proves MySQL-specific SQL behavior.

**Exercise:** Create a synthetic student through Swagger, read it by ID, delete it,
then explain which method and SQL operation each request triggers.

## 2. Docker: package the app

An image is a packaged filesystem/configuration. A container is a running instance
of that image. Docker makes the runtime portable, but does not make configuration,
credentials or external services automatic.

The Dockerfile has a build path using Maven and a runtime path using only a JRE.
The existing project already had this idea. The extension adds a non-root user,
Maven cache mounts, a CI target that accepts the tested JAR, and a small build context.
Compose starts MySQL and the application locally; a database health check prevents
the ordinary startup-order race. The database has a named volume and no host port.

The API no longer serializes reverse JPA collections (`Student.enrollments`,
`Department.students`, `Course.enrollments`). This prevents recursive graphs and lazy
collection loading after the service transaction has ended. Forward references are
retained. A production API should use explicit DTOs rather than expose JPA entities.

**Interview: Why not run Maven in the deployed container?**
Compilation needs a JDK/build tools; execution needs the packaged JAR and a JRE.
Keeping build tools out reduces size and unnecessary installed software. A smaller
image still needs scanning; a vulnerable JAR remains vulnerable in a small image.

**Interview: What does caching improve?**
Maven dependency caching avoids downloading the same artifacts. Docker layer caching
reuses unchanged build steps. Putting frequently changing source after stable metadata
reduces cache invalidation. In this CI target, the JAR is already built/tested, so the
Docker job mainly reuses its base/runtime layers and copies the changed JAR.

**Exercise:** Change one Java line, rebuild, and identify which steps rerun. Measure
instead of guessing. Never assume a base image tagged `17-jre-alpine` is permanently safe.

## 3. GitHub Actions: automate checks and delivery

A workflow runs jobs on runner machines. `needs` expresses prerequisites. The first
three jobs can run concurrently; Docker waits for all three, Trivy waits for Docker,
and deploy waits for Trivy. Failing a command fails its step/job because the workflow
does not suppress the failure. PR jobs get no cloud deployment identity.

**Interview: What is the difference between the three scanners?**
Gitleaks detects credentials in source/history. Checkov checks infrastructure policy
such as exposed SSH. Trivy scans the image's operating-system and language packages
against vulnerability data. None replaces functional tests or proves no vulnerabilities
exist. Trivy severity is not a universal severity model for every tool.

**Interview: How do you know the scanned image is deployed?**
The build exports a single image tar and checksum. Scan and deploy jobs download and
verify that artifact. Deployment loads and pushes it without rebuilding, obtains its
registry digest, and sets that immutable digest in the manifest.

**Interview: Why not use latest?**
A tag can move. A digest identifies image content. A commit tag helps traceability,
while deployment by digest removes ambiguity about which image content was selected.

**Interview: Why OIDC?**
GitHub proves the job's identity to Azure using a short-lived federated token. Azure
issues a temporary access token matching the configured trust and role permissions.
There is no client secret to store and periodically rotate in GitHub. The environment
subject must be combined with a master-only environment policy and workflow protection.

## 4. Terraform: describe Azure resources

Terraform configuration describes desired resources. A plan compares that description,
state and Azure's current responses. Apply makes the approved changes. State maps
configuration addresses to real Azure resource IDs; losing it is an operational issue.

**Interview: What is a VNet, subnet and NSG?**
A VNet is an Azure network boundary, a subnet is an address range within it, and an
NSG filters network traffic. This lab permits the owner's IP on SSH and the app's
NodePort, while keeping the Kubernetes management API closed to internet clients.

**Interview: Why a VM with k3s rather than AKS?**
It makes a small lab's components visible and keeps management simple. The tradeoff
is that I operate/patch the VM and Kubernetes myself, with one failure domain. It
does not provide AKS's managed control plane, and a small cost estimate is not a
guarantee of free operation. VM/disk/IP/registry charges must be checked.

**Interview: Why do the cluster CIDRs differ from the VNet?**
Overlapping address ranges can break routing. The VNet uses 10.42/16, while k3s uses
10.52/16 for pods and 10.53/16 for services.

**Interview: How does GitHub deploy without public SSH/Kubernetes access?**
It calls Azure Run Command over Azure's API. The VM agent executes the trusted bundle
locally, then k3s's local kubectl applies the manifests. The GitHub role is scoped to
one VM, but is root-equivalent there. This convenience is an explicit lab tradeoff.

## 5. Kubernetes: keep the containers running

A Pod groups containers; a Deployment maintains desired application replicas and
rollouts. A Service selects pods through labels and provides a stable destination.
NodePort exposes a service on a node port (30089 here). The Azure NSG still decides
who can reach that node port externally.

**Interview: Readiness, liveness and startup probes?**
Startup allows time to initialize before ordinary checks. Readiness decides whether
the pod receives service traffic and includes database health. Liveness decides when
to restart an unhealthy application and deliberately excludes the database, so a
database outage does not cause a storm of pointless application restarts.

**Interview: Why CPU/memory requests and limits?**
Requests help scheduling and baseline allocation; limits constrain consumption.
Exceeding a CPU limit normally throttles; exceeding a memory limit can kill the process.
JVM heap is only part of Java memory, so the configured heap percentage leaves headroom.

**Interview: What survives a pod restart?**
The MySQL PVC stores its data outside the container writable layer. On this single
node it is still local disk storage: it survives pod replacement but not arbitrary
VM/disk loss. Backups must be copied off the VM and restored in a test to be trusted.

**Interview: Is a Kubernetes Secret encrypted?**
Its manifest values are base64 encoded, which is reversible. k3s secret encryption
at rest protects stored secrets, but authorized administrators can still retrieve
them. Here passwords are generated on the VM and never checked into Git.

## 6. Metrics: observe behavior

Actuator exposes health and metrics on internal port 9090. Micrometer translates
application/JVM measurements to Prometheus format. Prometheus scrapes and stores
time series; Grafana queries them and renders charts. Metrics differ from logs,
which record individual events, and traces, which connect work across requests/services.

**Interview: Which signals would you watch?**
Availability, request rate, error rate and latency, followed by CPU, memory and JVM
heap. High p95 latency means the slow tail has grown; averages can conceal it.
No traffic and a down application are different situations. Check scrape health too.

**Interview: What did you improve?**
Answer with actual diffs and evidence. A safe starting account is: “I extended my
Spring Boot/Jenkins/Minikube school project with a GitHub Actions security pipeline,
Terraform for Azure, a k3s deployment and metrics. I separated build and runtime
credentials, deployed the scanned artifact by digest and documented the single-node
tradeoffs.” Add “deployed” or numerical savings only after successful cloud runs.

## Practice debugging aloud

1. Trivy fails: read package/CVE/fixed-version details; update the affected base or
   dependency, rebuild and rescan. Do not solve it by setting exit-code to zero.
2. App is Pending: inspect scheduling events, resource requests, PVC and node state.
3. App runs but API fails: inspect readiness, Service selectors/endpoints, MySQL and NSG.
4. ImagePullBackOff: inspect digest, AcrPull role and registry token renewal.
5. Deploy job is green but service fails: distinguish CLI API acceptance from guest
   command success, rollout readiness and real smoke test results.
6. Disk/VM loss: PVC alone is insufficient; explain how the off-VM backup is restored.

For every stage, explain the problem, your choice, a rejected alternative, the
evidence that it works and a remaining limitation. That is stronger than memorizing
tool definitions or repeating the original résumé figures.
