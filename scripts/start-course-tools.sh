#!/bin/bash
# Bootstrap on the Azure tools VM. Public HTTPS is an explicit second step.
set -euo pipefail
umask 077
mode=${1:-bootstrap}
[[ "$EUID" -eq 0 ]] || { echo 'Run with sudo on the Azure tools VM.' >&2; exit 1; }
[[ "$mode" == bootstrap || "$mode" == https ]]
root=$(cd "$(dirname "$0")/.." && pwd)
destination=/opt/student-tools
mkdir -p "$destination"
cp "$root/cloud/tools/compose.yml" "$root/cloud/tools/Caddyfile" "$destination/"
if [[ ! -f "$destination/.env" ]]; then
  printf 'SONAR_DB_PASSWORD=%s\n' "$(openssl rand -hex 32)" > "$destination/.env"
fi
chmod 600 "$destination/.env"
cd "$destination"
if [[ "$mode" == bootstrap ]]; then
  docker compose up -d postgres sonarqube nexus
  echo 'Bootstrap started. Use SSH tunnels to change admin passwords and disable anonymous access before HTTPS.'
else
  fqdn=${2:?Pass the Azure tools_fqdn output after completing authenticated bootstrap}
  [[ "$fqdn" =~ ^[a-z0-9][a-z0-9.-]+\.cloudapp\.azure\.com$ ]]
  sed -i '/^SONAR_DOMAIN=/d; /^NEXUS_DOMAIN=/d' .env
  printf 'SONAR_DOMAIN=%s\nNEXUS_DOMAIN=%s:8443\n' "$fqdn" "$fqdn" >> .env
  docker compose --profile https up -d
  echo "SonarQube: https://$fqdn ; Nexus: https://$fqdn:8443"
fi
