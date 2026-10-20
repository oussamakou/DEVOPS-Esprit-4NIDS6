#!/bin/bash
# Ephemeral GitHub runner only. Does not use Azure or touch an existing cluster.
set -euo pipefail
[[ "${GITHUB_ACTIONS:-}" == true ]] || { echo 'This disposable-cluster test is restricted to GitHub runners.' >&2; exit 1; }
image=$1
[[ "$image" =~ ^student-management:[a-f0-9]{40}$ ]]
work=$(mktemp -d)
umask 077
cleanup() {
  status=$?
  if [ "$status" -ne 0 ]; then
    kubectl -n student get pods,services,pvc || true
    kubectl -n student get events --sort-by=.lastTimestamp || true
    kubectl -n student logs deployment/student-app --tail=80 || true
    kubectl -n student logs deployment/mysql --tail=50 || true
    kubectl -n student logs deployment/grafana --tail=100 || true
    kubectl -n student logs deployment/grafana --previous --tail=60 || true
    kubectl -n student logs deployment/prometheus --tail=60 || true
    kubectl -n student get pods -o json | jq '[.items[] | {name:.metadata.name,containers:[.status.containerStatuses[]? | {name,state,lastState}]}]' || true
  fi
  [ -z "${prom_pid:-}" ] || kill "$prom_pid" 2>/dev/null || true
  .tools/k3d cluster delete student-ci || true
  rm -rf "$work"
  exit "$status"
}
trap cleanup EXIT
.tools/k3d cluster create student-ci --image rancher/k3s:v1.37.1-k3s1 \
  --port '127.0.0.1:30089:30089@server:0' --wait --timeout 180s \
  --k3s-arg '--disable=traefik@server:*' --k3s-arg '--disable=servicelb@server:*'
.tools/k3d image import "$image" --cluster student-ci
# Use the explicit context; do not let subsequent commands select a user's cluster.
export KUBECONFIG="$work/kubeconfig"
.tools/k3d kubeconfig get student-ci > "$KUBECONFIG"
kubectl apply -f k8s/namespace.yaml
printf 'mysql-root-password=%s\nmysql-password=%s\n' "$(openssl rand -hex 32)" "$(openssl rand -hex 32)" > "$work/mysql.env"
kubectl -n student create secret generic mysql-secret --from-env-file="$work/mysql.env"
printf 'admin-password=%s\n' "$(openssl rand -hex 32)" > "$work/grafana.env"
kubectl -n student create secret generic grafana-admin --from-env-file="$work/grafana.env"
printf '{"auths":{}}' > "$work/dockerconfig.json"
kubectl -n student create secret generic acr-pull --type=kubernetes.io/dockerconfigjson --from-file=.dockerconfigjson="$work/dockerconfig.json"
kubectl apply -f k8s/mysql-deployment.yaml -f k8s/network-policy.yaml -f k8s/egress-policy.yaml
sed "s|IMAGE_PLACEHOLDER|$image|g" k8s/deployment.yaml | kubectl apply -f -
kubectl -n student rollout status deployment/mysql --timeout=300s
kubectl -n student rollout status deployment/student-app --timeout=300s
curl --fail --silent --show-error -H 'Content-Type: application/json' \
  -d '{"firstName":"Pipeline","lastName":"PersistenceCheck","email":"ci@example.test"}' \
  http://127.0.0.1:30089/student/students/createStudent > /dev/null
curl --fail --silent http://127.0.0.1:30089/student/students/getAllStudents | jq -e 'any(.[]; .email == "ci@example.test")'

# Test actual PVC persistence, rather than merely checking that a PVC object exists.
kubectl -n student delete pod -l app=mysql --wait=true
kubectl -n student rollout status deployment/mysql --timeout=300s
for attempt in $(seq 1 40); do
  if curl --fail --silent http://127.0.0.1:30089/student/students/getAllStudents > "$work/students.json" \
    && jq -e 'any(.[]; .email == "ci@example.test")' "$work/students.json" > /dev/null; then break; fi
  sleep 3
done
jq -e 'any(.[]; .email == "ci@example.test")' "$work/students.json"

kubectl apply -f monitoring/
kubectl -n student rollout status deployment/prometheus --timeout=240s
kubectl -n student rollout status deployment/grafana --timeout=240s
kubectl -n student port-forward service/prometheus 9091:9090 > "$work/prometheus-forward.log" 2>&1 &
prom_pid=$!
healthy=false
for attempt in $(seq 1 40); do
  if curl --fail --silent 'http://127.0.0.1:9091/api/v1/targets' > "$work/targets.json" \
    && jq -e 'any(.data.activeTargets[]; .labels.job == "student-api" and .health == "up")' "$work/targets.json" > /dev/null; then
    healthy=true
    break
  fi
  sleep 3
done
"$healthy"
echo 'K3S_SMOKE_PASSED: API CRUD, MySQL pod replacement/persistence, probes and Prometheus target UP.'
