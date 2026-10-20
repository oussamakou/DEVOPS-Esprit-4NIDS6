#!/bin/bash
# Root-only script: refresh registry credentials hourly using the VM managed identity.
set -euo pipefail
umask 077
registry=$(cat /etc/student-lab/registry)
[[ "$registry" =~ ^[a-z0-9]+\.azurecr\.io$ ]]
identity=$(curl --fail --silent --show-error --retry 5 --retry-delay 5 --connect-timeout 5 --max-time 60 \
  -H Metadata:true 'http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fmanagement.azure.com%2F')
token=$(jq -er .access_token <<< "$identity")
# IMDS does not promise tenant_id in its response. The signed token carries tid.
tenant=$(jq -ner --arg token "$token" '$token | split(".")[1] | gsub("-"; "+") | gsub("_"; "/") | . + ("=" * ((4 - (length % 4)) % 4)) | @base64d | fromjson | .tid')
refresh=$(curl --fail --silent --show-error --retry 5 --retry-delay 5 --connect-timeout 10 --max-time 120 \
  -X POST "https://$registry/oauth2/exchange" \
  --data-urlencode grant_type=access_token --data-urlencode "service=$registry" \
  --data-urlencode "tenant=$tenant" --data-urlencode "access_token=$token" | jq -er .refresh_token)
config=$(mktemp)
trap 'rm -f "$config"' EXIT
jq -n --arg server "$registry" --arg credential "$(printf '00000000-0000-0000-0000-000000000000:%s' "$refresh" | base64 -w0)" \
  '{auths:{($server):{auth:$credential}}}' > "$config"
k3s kubectl -n student create secret generic acr-pull --type=kubernetes.io/dockerconfigjson \
  --from-file=.dockerconfigjson="$config" --dry-run=client -o yaml | k3s kubectl apply -f - > /dev/null
