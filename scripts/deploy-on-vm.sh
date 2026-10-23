#!/bin/bash
set -euo pipefail
umask 077
work=$1
image=$2
command -v k3s >/dev/null
k3s kubectl wait node --all --for=condition=Ready --timeout=180s
k3s kubectl apply -f "$work/k8s/namespace.yaml"

# Create once; preserve credentials so reruns still match the existing MySQL volume.
if ! k3s kubectl -n student get secret mysql-secret >/dev/null 2>&1; then
  {
    printf 'mysql-root-password=%s\n' "$(openssl rand -hex 32)"
    printf 'mysql-password=%s\n' "$(openssl rand -hex 32)"
  } > "$work/mysql.env"
  k3s kubectl -n student create secret generic mysql-secret --from-env-file="$work/mysql.env"
  rm "$work/mysql.env"
fi
if ! k3s kubectl -n student get secret grafana-admin >/dev/null 2>&1; then
  printf 'admin-password=%s\n' "$(openssl rand -hex 32)" > "$work/grafana.env"
  k3s kubectl -n student create secret generic grafana-admin --from-env-file="$work/grafana.env"
  rm "$work/grafana.env"
fi

install -d -m 700 /etc/student-lab
printf '%s\n' "${image%%/*}" > /etc/student-lab/registry
install -m 700 "$work/refresh-acr-secret.sh" /usr/local/sbin/refresh-acr-secret
cat > /etc/systemd/system/student-acr-refresh.service <<'UNIT'
[Unit]
Description=Refresh student registry pull credentials using Azure managed identity
After=k3s.service network-online.target
Wants=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/refresh-acr-secret
UNIT
cat > /etc/systemd/system/student-acr-refresh.timer <<'UNIT'
[Unit]
Description=Renew student image pull credentials every hour
[Timer]
OnBootSec=2min
OnUnitActiveSec=1h
Persistent=true
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
# RBAC assignments may take time to propagate on the first deployment.
ready=false
for attempt in $(seq 1 12); do
  if /usr/local/sbin/refresh-acr-secret; then ready=true; break; fi
  sleep 10
done
"$ready"
systemctl enable --now student-acr-refresh.timer

k3s kubectl apply -f "$work/k8s/"
k3s kubectl -n student rollout status deployment/mysql --timeout=300s
k3s kubectl -n student rollout status deployment/student-app --timeout=300s
# This exercises the actual NodePort -> Service -> app -> database path.
curl --fail --silent --show-error --retry 10 --retry-delay 3 --retry-connrefused \
  http://127.0.0.1:30089/student/students/getAllStudents > /dev/null
k3s kubectl apply -f "$work/monitoring/"
k3s kubectl -n student rollout status deployment/prometheus --timeout=180s
k3s kubectl -n student rollout status deployment/grafana --timeout=180s
printf 'DEPLOY_SUCCEEDED %s\n' "$image"
