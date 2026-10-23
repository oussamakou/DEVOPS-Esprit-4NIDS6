# Operate, observe and recover the lab

## Check a deployment

SSH into the VM with your owner key. These commands run on that Linux VM:

```bash
sudo k3s kubectl -n student get deployments,pods,services,pvc
sudo k3s kubectl -n student rollout status deployment/student-app
sudo k3s kubectl -n student logs deployment/student-app --tail=100
sudo k3s kubectl -n student get events --sort-by=.lastTimestamp
sudo systemctl status student-acr-refresh.timer
sudo journalctl -u student-acr-refresh.service --since '2 hours ago'
curl --fail http://127.0.0.1:30089/student/students/getAllStudents
```

`ImagePullBackOff`: inspect pod events, registry name, VM AcrPull role and credential
renewal timer. Run `sudo /usr/local/sbin/refresh-acr-secret` and retry a rollout after
fixing permissions. Do not solve it by enabling registry admin passwords.

`CrashLoopBackOff`: inspect the app's previous logs, database readiness and memory
limits. `OOMKilled` means the process exceeded its memory allocation. Increasing
probes does not fix an out-of-memory condition.

`Pending` MySQL: inspect PVC status, local-path provisioner and node disk space.
The deployment uses Recreate because one local ReadWriteOnce data volume must not
be concurrently mounted by two active MySQL processes during a rolling update.

Readiness failure due to MySQL removes the application from service without repeatedly
restarting it. Liveness deliberately does not depend on database health.

## Grafana and Prometheus access

On the VM, run these in separate SSH terminals:

```bash
sudo k3s kubectl -n student port-forward --address 127.0.0.1 service/grafana 3000:3000
sudo k3s kubectl -n student port-forward --address 127.0.0.1 service/prometheus 9091:9090
```

On Windows, open an SSH tunnel and keep it running:

```powershell
$ip = .tools/terraform -chdir=terraform output -raw public_ip
ssh -i "$env:USERPROFILE/.ssh/student-azure" -N -L 3000:127.0.0.1:3000 -L 9091:127.0.0.1:9091 "azureuser@$ip"
```

Open `http://localhost:3000` and `http://localhost:9091/targets`. Prometheus's target
must be UP. The Actuator management port has no `/student` prefix because it uses
a separate web server: its scrape path is `/actuator/prometheus`.

Retrieve Grafana's generated admin password privately over SSH on the VM:

```bash
sudo k3s kubectl -n student get secret grafana-admin -o jsonpath='{.data.admin-password}' | base64 -d
printf '\n'
```

Use username `admin`; do not paste the password into issues or commit it. The
provisioned Student API dashboard contains availability, request rate, 5xx rate,
p95 latency, JVM heap and CPU. Send API traffic for at least a few minutes for rate
queries to become useful. No traffic can produce blank rates; it does not prove an outage.
The availability panel and the `/targets` page distinguish these cases.

## Roll back the application

```bash
sudo k3s kubectl -n student rollout history deployment/student-app
sudo k3s kubectl -n student rollout undo deployment/student-app
sudo k3s kubectl -n student rollout status deployment/student-app --timeout=300s
curl --fail http://127.0.0.1:30089/student/students/getAllStudents
```

Revert the offending commit too; otherwise the next successful master run reapplies
it. The pipeline reports a failure on bad rollout but does not automatically guess
which version is safe. Rollback restores an earlier pod template, not database data
or schema. `ddl-auto=update` is retained for the learning app; introduce explicit
schema migrations and compatibility discipline for a real deployment.

## Back up MySQL and test recovery

Copy `scripts/backup-mysql.sh` onto the VM using scp, then run it with sudo. It writes
a private gzip SQL dump under `/var/backups/student/`. Copy the backup off the VM;
a backup on the same disk is not protection against losing that VM/disk.

For example, after noting the exact backup filename, make only that file available
to the owner for export:

```bash
sudo cp /var/backups/student/EXACT_FILENAME.sql.gz /home/azureuser/
sudo chown azureuser:azureuser /home/azureuser/EXACT_FILENAME.sql.gz
sudo chmod 600 /home/azureuser/EXACT_FILENAME.sql.gz
```

Then use scp from Windows with your SSH key. Store it privately. A backup is unproven
until restored into an isolated test database and checked. On the VM, create an
isolated database and restore a chosen file into it (never aim this at studentdb):

```bash
sudo k3s kubectl -n student exec deployment/mysql -- sh -ec \
  'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -e "CREATE DATABASE studentdb_restore_test"'
sudo gzip -dc /var/backups/student/EXACT_FILENAME.sql.gz | \
  sudo k3s kubectl -n student exec -i deployment/mysql -- sh -ec \
  'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot studentdb_restore_test'
sudo k3s kubectl -n student exec deployment/mysql -- sh -ec \
  'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot studentdb_restore_test -e "SHOW TABLES; SELECT COUNT(*) FROM student;"'
```

Verify expected rows and relationships before planning a real restore. The above
creates an additional database; it does not replace the live database.

## Local Docker troubleshooting

- A working `docker --version` checks the client only. `docker info` must reach a server.
- If Docker Desktop reports an inaccessible `dockerInference` or `engine.sock`,
  preserve Docker data. These are host service sockets, not application files. Exit
  Docker, inspect its host logs, and move only a confirmed stale socket aside using
  WSL if Windows cannot handle its reparse point. Do not factory reset or delete the
  Docker data disk to solve this symptom. Preserve the exact error for diagnosis.
- An old mysql_data volume keeps the original password/user setup even when `.env`
  changes. Changing environment variables is not password rotation. Back up data and
  update users/passwords via SQL, or explicitly discard the old volume only if its
  data is disposable. `docker compose down` preserves it; adding `-v` deletes it.
- For port conflicts, change only the host side of the local Compose port mapping.
- On HTTP failures, check `docker compose ps` and `docker compose logs mysql app`
  before changing network security rules.

## Prove a security gate safely

For Checkov, run `python scripts/prove-ssh-gate.py` in an environment with Checkov
installed. On Windows, use the Checkov environment's Python and pass its
`Scripts/checkov` launcher as the script argument. This creates a temporary fixture
outside `terraform/` with internet-wide SSH, verifies that CKV_LAB_1 rejects it,
and removes it. The built-in SSH check in the pinned scanner did not reject the
literal /0 case, which is why the project supplies and tests an additional policy.
The workflow repeats this negative test. No fixture is applied to Azure.
For Gitleaks, use a synthetic fixture that matches a documented test rule, never a
real credential. For Trivy, retain an actual report and fix the identified package
or base image version. A multi-stage build alone does not remove vulnerable Java
libraries packaged inside the application JAR.
