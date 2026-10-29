#!/bin/bash
# Run on a dedicated Azure Docker host as root, via Azure Run Command.
set -euo pipefail
umask 077
mode=$1
bundle=$2
image=$3
[[ "$mode" == deploy || "$mode" == monitor ]]
[[ "$image" =~ ^[a-z0-9]+\.azurecr\.io/student-management@sha256:[a-f0-9]{64}$ ]]
destination=/opt/student-course
docker compose version
command -v curl
command -v jq
if [[ "$mode" == deploy ]]; then
  # Never take over the existing k3s deployment. Use a separate Compose VM.
  if systemctl is-active --quiet k3s; then
    echo 'Use a dedicated Docker Compose VM; this host is running k3s.' >&2
    exit 1
  fi
  mkdir -p "$destination"
  # Separate exporter setup owns this discovery directory; deployments preserve it.
  install -d -m 755 "$destination/node-targets"
  # These tracked configurations contain no secrets. Non-root container users
  # must be able to read the bind mounts, even under our private umask.
  for config in "$bundle"/runtime/*; do
    install -m 644 "$config" "$destination/"
  done
  if [[ ! -f "$destination/.env" ]]; then
    printf 'MYSQL_ROOT_PASSWORD=%s\nDB_PASSWORD=%s\nGRAFANA_PASSWORD=%s\n' \
      "$(openssl rand -hex 32)" "$(openssl rand -hex 32)" "$(openssl rand -hex 32)" > "$destination/.env"
  fi
  chmod 600 "$destination/.env"
  # Replace only the image, preserving database credentials and volumes.
  sed -i '/^APP_IMAGE=/d' "$destination/.env"
  printf 'APP_IMAGE=%s\n' "$image" >> "$destination/.env"
  export DOCKER_CONFIG
  DOCKER_CONFIG=$(mktemp -d)
  trap 'rm -rf "$DOCKER_CONFIG"' EXIT
  registry=${image%%/*}
  identity=$(curl --fail --silent --show-error --retry 5 --connect-timeout 5 --max-time 60 \
    -H Metadata:true 'http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fmanagement.azure.com%2F')
  token=$(jq -er .access_token <<< "$identity")
  tenant=$(jq -ner --arg token "$token" '$token | split(".")[1] | gsub("-"; "+") | gsub("_"; "/") | . + ("=" * ((4 - (length % 4)) % 4)) | @base64d | fromjson | .tid')
  refresh=$(curl --fail --silent --show-error --connect-timeout 10 --max-time 120 \
    -X POST "https://$registry/oauth2/exchange" \
    --data-urlencode grant_type=access_token --data-urlencode "service=$registry" \
    --data-urlencode "tenant=$tenant" --data-urlencode "access_token=$token" | jq -er .refresh_token)
  printf '%s' "$refresh" | docker login "$registry" --username 00000000-0000-0000-0000-000000000000 --password-stdin > /dev/null
  cd "$destination"
  docker compose pull
  docker compose up -d --remove-orphans --wait --wait-timeout 300
fi
cd "$destination"
# Both readiness and a real database-backed API request must pass.
ready=false
for attempt in $(seq 1 60); do
  if curl --fail --silent --max-time 5 http://127.0.0.1:8089/student/students/getAllStudents > /tmp/student-course-smoke.json \
    && jq -e 'type == "array"' /tmp/student-course-smoke.json > /dev/null; then
    ready=true
    break
  fi
  sleep 3
done
if [[ "$ready" != true ]]; then
  echo 'API_READINESS_FAILED: localhost:8089 did not return a database-backed JSON array.' >&2
  docker compose ps -a >&2
  # Print state and port mappings only: never dump container environment secrets.
  docker inspect --format 'status={{.State.Status}} oom={{.State.OOMKilled}} ports={{json .NetworkSettings.Ports}}' \
    "$(docker compose ps -a -q app)" >&2
  exit 1
fi
container=$(docker compose ps -q app)
[[ -n "$container" ]]
[[ "$(docker inspect --format '{{.Config.Image}}' "$container")" == "$image" ]]
if [[ "$mode" == monitor ]]; then
  shopt -s nullglob
  node_files=("$destination"/node-targets/*.json)
  expected_nodes=0
  if [[ ${#node_files[@]} -gt 0 ]]; then
    expected_nodes=$(jq -se '[.[][] | .targets[]] | length' "${node_files[@]}")
  fi
  healthy=false
  for attempt in $(seq 1 40); do
    if curl --fail --silent --max-time 5 http://127.0.0.1:9091/api/v1/targets \
      | jq -e --argjson expected "$expected_nodes" '.data.activeTargets | any(.[]; .labels.job == "student-api" and .health == "up") and ([.[] | select(.labels.job == "azure-nodes")] | length) == $expected and all(.[]; .labels.job != "azure-nodes" or .health == "up")' > /dev/null \
      && curl --fail --silent --max-time 5 http://127.0.0.1:3000/api/health | jq -e '.database == "ok"' > /dev/null; then
      healthy=true
      break
    fi
    sleep 3
  done
  if [[ "$healthy" != true ]]; then
    echo 'MONITORING_FAILED: API/node scrape target or Grafana database is not healthy.' >&2
    docker compose ps -a >&2
    exit 1
  fi
  echo 'MONITORING_VERIFIED: API and configured node targets UP; Grafana database ok'
fi
# The caller checks this marker; Azure request success alone is insufficient.
echo "DEPLOY_SUCCEEDED compose-$mode $image"
