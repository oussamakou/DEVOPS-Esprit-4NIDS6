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
  cp "$bundle"/runtime/* "$destination/"
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
"$ready"
container=$(docker compose ps -q app)
[[ -n "$container" ]]
[[ "$(docker inspect --format '{{.Config.Image}}' "$container")" == "$image" ]]
if [[ "$mode" == monitor ]]; then
  healthy=false
  for attempt in $(seq 1 40); do
    if curl --fail --silent --max-time 5 http://127.0.0.1:9091/api/v1/targets \
      | jq -e 'any(.data.activeTargets[]; .labels.job == "student-api" and .health == "up")' > /dev/null \
      && curl --fail --silent --max-time 5 http://127.0.0.1:3000/api/health | jq -e '.database == "ok"' > /dev/null; then
      healthy=true
      break
    fi
    sleep 3
  done
  "$healthy"
  echo 'MONITORING_VERIFIED: Prometheus student-api UP and Grafana database ok'
fi
# The caller checks this marker; Azure request success alone is insufficient.
echo "DEPLOY_SUCCEEDED compose-$mode $image"
