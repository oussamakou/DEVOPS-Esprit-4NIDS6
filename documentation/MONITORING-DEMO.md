# Opening and explaining the monitoring dashboards

## What currently collects metrics

The application exposes Prometheus metrics with Spring Boot Actuator and
Micrometer at `http://app:9090/actuator/prometheus` inside Docker. Prometheus
scrapes this endpoint every 15 seconds under the job name `student-api`.
Grafana queries Prometheus through its provisioned Prometheus data source.

| Existing panel | What it measures |
| --- | --- |
| API scrape availability | Whether Prometheus successfully scraped the app metrics endpoint (`up` is 1 or 0). This is not a complete business/API health check. |
| Requests / second | Rate of HTTP requests, excluding the configured Actuator URI pattern. |
| 5xx responses / second | Rate of server-error responses, when that status series exists. No data can mean no 5xx series was created; it is not proof of a measured zero. |
| 95th percentile request latency | Estimated p95 duration from HTTP histogram buckets over five minutes. |
| JVM heap usage | Memory the application's Java heap is using. |
| Process CPU | CPU usage reported for the Java application process. |

Prometheus keeps the runtime data in a named Docker volume, with retention limits
of 24 hours and 256 MB. Grafana stores its own configuration separately. The
runtime configuration has two jobs: `student-api` and `azure-nodes`.

Node Exporter adds Linux host metrics for the application VM and the separate
SonarQube/Nexus tools VM. Its separate **Azure VMs - Node Exporter** dashboard
shows host CPU, RAM, root filesystem usage, network receive/transmit, disk
throughput and uptime. Both VM lines are labelled by `host` (`application-vm`
and `tools-vm`). Do not describe the existing Java CPU/heap panels as whole-VM
monitoring. There is no MySQL exporter or cAdvisor in this configuration.

The exporter runs in its own Compose project on each VM with host network/PID
namespaces and read-only host mounts, following the official host-monitoring
container layout. It runs as a non-root user, with all Linux capabilities dropped,
a read-only container filesystem and a memory/CPU limit. Only the required
collectors are enabled. Port 9100 listens on each VM's **private** `10.42.x.x`
address; no public port or NSG Internet rule is added. Node metrics do not imply
that SonarQube/Nexus themselves are healthy: exporter UP confirms a successful
scrape of host telemetry.

## Open the dashboards

From Windows PowerShell, after confirming that SSH access to the app VM works:

```powershell
powershell -NoProfile -File C:\Users\oussa\.ssh\student-course-open-dashboards.ps1
```

Then open:

- Prometheus targets: http://127.0.0.1:9091/targets
- Prometheus query page: http://127.0.0.1:9091/query
- Grafana: http://127.0.0.1:3000/d/student-devsecops
- Azure VM dashboard: http://127.0.0.1:3000/d/student-vms
- Application read request: http://127.0.0.1:8089/student/students/getAllStudents

These localhost ports are SSH forwards to Azure, not local instances of the
application. They require the app VM to be running and its SSH rule to allow your
current public IP. Changing between home and campus networks can change that IP.
The private Grafana credentials are documented outside Git in the owner's
`.ssh/student-course-credentials.md`. Keep that file off the shared screen.

## Demonstration order

1. In Prometheus Targets, point to `student-api`, its endpoint and its UP state.
2. In the query page, evaluate `up{job="student-api"}`. Explain that 1 means the
   scrape succeeded, rather than claiming every API operation is healthy.
3. Open Grafana's Student API dashboard. Select the last 15 or 30 minutes and
   choose an available refresh interval, such as 10 seconds. Prometheus still
   collects new samples every 15 seconds. Point to requests, latency, Java heap
   and process CPU.
4. Generate a small number of read-only API requests, then wait for scrapes and
   watch the request rate/latency panels. Avoid deliberately breaking the service
   to make the error panel display something.
5. Open **Azure VMs - Node Exporter**. Show both VM lines and distinguish host
   memory from Java heap. New rate panels require at least two scrapes; allow
   about 30 seconds after installation. In Prometheus, show all three targets:
   the application and the two exporters.

Useful query copied from the actual dashboard:

```promql
sum(rate(http_server_requests_seconds_count{application="student-management",uri!~"/actuator.*"}[5m]))
```

## A short explanation to give the professor

"My application exports metrics through Actuator and Micrometer. Prometheus polls
that endpoint every 15 seconds and stores time series. Grafana queries those time
series to display application availability, request rate, errors, latency, Java
heap and process CPU. Two Node Exporters additionally expose Linux host CPU,
memory, disk, network and uptime for the application VM and the tools VM. Their
endpoints stay private inside Azure."

## Install or reproduce the host monitoring

### Image selection evidence (2026-10-29)

Trivy 0.76.0 rejected the latest stable image `prom/node-exporter:v1.12.1`
with **15 HIGH** findings in its Go runtime/dependencies. The newer official
upstream `master` build created on 2026-10-24 had **0 HIGH/CRITICAL** findings in
the same scan. The Compose file pins that build's immutable image digest:
`sha256:60717af57d790f02db92fdaad1175c86820e5e44ad4e35bfce543fd125b0da43`.
This is a development build, rather than a stable release; it is being used in
this learning lab after live metric validation. Reassess a patched stable release
when available. A clean severity-filtered scan does not prove there are no other
vulnerabilities. Both raw reports are preserved as standalone evidence.

Use the current repository checkout on each VM. On **each** VM:

```bash
sudo bash scripts/install-node-exporter.sh
```

The installer discovers the private IP through Azure Instance Metadata and
refuses addresses outside the lab subnets. On the **application** VM, discover
the actual private addresses from Azure (do not assume the dynamic IPs), then run:

```bash
sudo bash scripts/update-vm-monitoring.sh APP_PRIVATE_IP TOOLS_PRIVATE_IP
python3 scripts/check-node-monitoring.py
```

Replace the two uppercase arguments with the actual private IPv4 addresses.
This updates only Prometheus/Grafana, saving configuration backups under
`/opt/student-course/monitoring-backups/`. It preserves the deployed application,
database containers, volumes and private `.env`. The two node targets are stored
under `/opt/student-course/node-targets/azure-vms.json`. The CI deployment bundle
preserves this discovery directory and includes the VM dashboard. The monitoring
stage fails if a configured exporter is missing or DOWN.

If Azure assigns a different private IP after a VM is recreated, rerun the
exporter installer there and update the target file from the application VM.
The exporter is a separate Compose project, so the application deployment's
`--remove-orphans` cannot delete it. To roll back the exporter, use
`sudo docker compose -f /opt/student-node-exporter/compose.yml down` on each VM
and remove the corresponding entry from node discovery. No volume removal is
needed. Monitoring email alerts remain separate work: the configured email
notification is for pipeline results, and no host alert rules are added here.

Sources in this repository: `cloud/runtime/prometheus.yml`,
`cloud/runtime/datasources.yml`, `cloud/runtime/compose.yml` and
`monitoring/dashboard.yaml`. Node Exporter reference:
https://prometheus.io/docs/guides/node-exporter/.
