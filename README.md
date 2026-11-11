# DevSecOps coursework: Spring Boot student management

The coursework pipeline runs on GitHub-hosted runners and demonstrates Development, Acceptance, Production smoke testing, and Operations monitoring in a disposable Docker Compose lab.

**Start with [the professor demo guide](documentation/PROFESSOR-DEMO.md)** for the current workflow and evidence. The [Azure coursework guide](documentation/COURSEWORK-PIPELINE.md) records the historical VM deployment and manual Azure workflow. The [setup and project guide](documentation/START-HERE.md) covers local and k3s setup.

- [Final coursework report](documentation/FINAL-REPORT.pdf)
- [Pre-build security reports](documentation/PREBUILD-SECURITY-REPORTS.md) and [Nmap network acceptance](documentation/NMAP-ACCEPTANCE.md)
- [Monitoring dashboards and Node Exporter](documentation/MONITORING-DEMO.md)
- [Learn the implementation and prepare for interviews](documentation/LEARNING-AND-INTERVIEW.md)
- [Provision Azure and configure GitHub OIDC](documentation/AZURE-SETUP.md)
- [Deploy, monitor, back up and roll back](documentation/OPERATIONS.md)
- [Security boundaries and documented exceptions](SECURITY.md)
- [Checks actually performed](documentation/VALIDATION.md)
- [Record real results before updating the CV](evidence/README.md)
- [Original Jenkins/Minikube project](documentation/LEGACY-JENKINS-MINIKUBE.md)

## Run locally

Use Java 17, Python 3 and Docker Desktop with Linux containers. From PowerShell:

```powershell
.\mvnw.cmd -B -ntp verify
powershell -ExecutionPolicy Bypass -File scripts/setup-local.ps1
docker compose up --build -d
Invoke-RestMethod http://localhost:8089/student/students/getAllStudents
```

The setup script creates ignored random database passwords. No Azure account is needed locally. The cloud deployment job stays skipped until its account and OIDC settings exist.

This is a single-node learning lab. Azure resources may incur charges; performance, image size and successful cloud deployment must be evidenced by real runs.
