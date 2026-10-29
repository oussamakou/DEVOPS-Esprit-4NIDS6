#!/bin/bash
# Apply monitoring only, preserving the running application, image and credentials.
set -euo pipefail
[[ "$EUID" -eq 0 ]] || { echo 'Run with sudo on the application VM.' >&2; exit 1; }
root=$(cd "$(dirname "$0")/.." && pwd)
destination=/opt/student-course
[[ -f "$destination/.env" ]] || { echo 'Deploy the application first.' >&2; exit 1; }
python3 "$root/scripts/configure-node-targets.py" "${1:?App private IP}" "${2:?Tools private IP}"
docker compose --project-directory "$destination" --env-file "$destination/.env" \
  -f "$root/cloud/runtime/compose.yml" config --quiet
prometheus_image=$(docker inspect --format '{{.Config.Image}}' \
  "$(docker compose -f "$destination/compose.yml" ps -q prometheus)")
docker run --rm --network none --entrypoint /bin/promtool \
  -v "$root/cloud/runtime/prometheus.yml:/etc/prometheus/prometheus.yml:ro" \
  -v "$destination/node-targets:/etc/prometheus/nodes:ro" \
  "$prometheus_image" check config /etc/prometheus/prometheus.yml
backup="$destination/monitoring-backups/$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 700 "$backup"
for config in compose.yml prometheus.yml vms.json; do
  if [[ -f "$destination/$config" ]]; then
    cp -p "$destination/$config" "$backup/"
  fi
done
install -m 644 "$root/cloud/runtime/compose.yml" "$destination/compose.yml"
install -m 644 "$root/cloud/runtime/prometheus.yml" "$destination/prometheus.yml"
install -m 644 "$root/monitoring/node-dashboard.json" "$destination/vms.json"
cd "$destination"
docker compose up -d --no-deps --force-recreate prometheus grafana
echo 'MONITORING_CONFIG_APPLIED: application and database containers preserved.'
