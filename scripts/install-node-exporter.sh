#!/bin/bash
# Run from this repository on either Azure VM: sudo bash scripts/install-node-exporter.sh
set -euo pipefail
[[ "$EUID" -eq 0 ]] || { echo 'Run with sudo on the Azure VM.' >&2; exit 1; }
root=$(cd "$(dirname "$0")/.." && pwd)
private_ip=$(curl --fail --silent --show-error --noproxy '*' --connect-timeout 5 --max-time 20 \
  -H Metadata:true 'http://169.254.169.254/metadata/instance/network/interface/0/ipv4/ipAddress/0/privateIpAddress?api-version=2021-02-01&format=text')
# Bind only the lab's private virtual network, never a wildcard/public address.
[[ "$private_ip" =~ ^10\.42\.[12]\.[0-9]{1,3}$ ]] || { echo 'Expected an Azure lab private IP.' >&2; exit 1; }
destination=/opt/student-node-exporter
install -d -m 755 "$destination"
install -m 644 "$root/cloud/node-exporter/compose.yml" "$destination/compose.yml"
umask 077
printf 'NODE_EXPORTER_PRIVATE_IP=%s\n' "$private_ip" > "$destination/.env"
cd "$destination"
docker compose config --quiet
docker compose pull
docker compose up -d --wait --wait-timeout 90
curl --fail --silent --show-error --noproxy '*' --max-time 10 "http://$private_ip:9100/metrics" \
  | grep '^node_exporter_build_info'
echo "NODE_EXPORTER_READY $(hostname) $private_ip:9100"
