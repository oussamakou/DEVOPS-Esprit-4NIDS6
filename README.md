# Azure DevSecOps: Spring Boot on Kubernetes

An Azure extension of the existing Esprit student-management project, with Terraform, a six-stage GitHub Actions security pipeline, k3s and Prometheus/Grafana.

**Start with [the setup and project guide](documentation/START-HERE.md).**

For the professor's checkout → Maven → SonarQube → Nexus → image → Azure Docker
Compose → monitoring → email sequence, use the [Azure coursework guide](documentation/COURSEWORK-PIPELINE.md).
It includes pre-commit hooks, commit SAST/dependency gates, a threat model and
[labelled failure evidence exercises](documentation/EVIDENCE-CAPTURE.md).

- [Learn the implementation and prepare for interviews](documentation/LEARNING-AND-INTERVIEW.md)
- [Provision Azure and configure GitHub OIDC](documentation/AZURE-SETUP.md)
- [Deploy, monitor, back up and roll back](documentation/OPERATIONS.md)
- [Security boundaries and documented exceptions](SECURITY.md)
- [Checks actually performed](documentation/VALIDATION.md)
- [Record real results before updating the CV](evidence/README.md)
- [Original Jenkins/Minikube project](documentation/LEGACY-JENKINS-MINIKUBE.md)

## Run locally

Use Java 17, Python 3 and Docker Desktop with Linux containers. From PowerShell:

`powershell
.\mvnw.cmd -B -ntp verify
powershell -ExecutionPolicy Bypass -File scripts/setup-local.ps1
docker compose up --build -d
Invoke-RestMethod http://localhost:8089/student/students/getAllStudents
`

The setup script creates ignored random database passwords. No Azure account is needed locally. The cloud deployment job stays skipped until its account and OIDC settings exist.

This is a single-node learning lab. Azure resources may incur charges; performance, image size and successful cloud deployment must be evidenced by real runs.
