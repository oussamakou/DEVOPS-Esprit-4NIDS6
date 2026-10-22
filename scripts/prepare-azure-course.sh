#!/bin/bash
# Azure Cloud Shell: generate private inputs and a reviewable plan, without applying it.
set -euo pipefail
trap 'status=$?; printf "Preparation stopped at line %s (exit %s). No apply command was run.\n" "$LINENO" "$status" >&2; exit "$status"' ERR
umask 077
admin_cidr=${1:?Usage: bash scripts/prepare-azure-course.sh YOUR_WORKSTATION_PUBLIC_IPV4/32}
export COURSE_ADMIN_CIDR="$admin_cidr"
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
echo '[1/7] Reading the Azure account (each account/provider request has a 120-second timeout)...'
timeout 120s az account show --query '{Name:name,State:state}' --output table
subscription=$(timeout 120s az account show --query id -o tsv)
export COURSE_LOCATION=${COURSE_LOCATION:-spaincentral}
export COURSE_APP_SIZE=${COURSE_APP_SIZE:-Standard_B2als_v2}
export COURSE_TOOLS_SIZE=${COURSE_TOOLS_SIZE:-Standard_D4s_v4}
for provider in Microsoft.Compute Microsoft.Network Microsoft.ContainerRegistry; do
  echo "[2/7] Checking provider: $provider..."
  state=$(timeout 120s az provider show --namespace "$provider" --query registrationState -o tsv)
  if [[ "$state" != Registered ]]; then
    echo "$provider is $state. Run: az provider register --namespace $provider --wait" >&2
    exit 1
  fi
done
echo '[3/7] Checking subscription VM eligibility...'
python3 scripts/check-azure-skus.py "$COURSE_LOCATION" "$COURSE_APP_SIZE" "$COURSE_TOOLS_SIZE"
echo '[4/7] Preparing SSH public key and private Terraform inputs...'
if [[ -z "${COURSE_PUBLIC_KEY:-}" ]]; then
  mkdir -p "$HOME/.ssh"
  key="$HOME/.ssh/student-course"
  if [[ ! -f "$key" ]]; then
    ssh-keygen -t ed25519 -f "$key" -N '' -C student-course > /dev/null
  fi
  COURSE_PUBLIC_KEY=$(cat "$key.pub")
fi
export COURSE_SUBSCRIPTION="$subscription"
export COURSE_PUBLIC_KEY
python3 - <<'PY'
import ipaddress, json, os
from pathlib import Path
cidr = ipaddress.ip_network(os.environ['COURSE_ADMIN_CIDR'], strict=True)
if cidr.version != 4 or cidr.prefixlen != 32 or not cidr.network_address.is_global:
    raise SystemExit('Use your workstation public IPv4 /32, not Cloud Shell IP or 0.0.0.0/0')
subscription = os.environ['COURSE_SUBSCRIPTION']
values = dict(subscription_id=subscription, prefix='studentcourse',
              location=os.environ['COURSE_LOCATION'],
              registry_name='studentcourse' + subscription.replace('-', '')[:12],
              admin_cidr=str(cidr), ssh_public_key=os.environ['COURSE_PUBLIC_KEY'],
              runtime='compose', enable_course_tools=True,
              vm_size=os.environ['COURSE_APP_SIZE'], tools_vm_size=os.environ['COURSE_TOOLS_SIZE'])
Path('terraform/coursework.auto-inputs.tfvars.json').write_text(json.dumps(values, indent=2))
PY
echo '[5/7] Downloading and verifying the pinned Terraform tool...'
python3 -u scripts/install-tools.py terraform
echo '[6/7] Initializing Terraform and validating configuration...'
.tools/terraform -chdir=terraform init -input=false
.tools/terraform -chdir=terraform workspace select -or-create coursework
.tools/terraform -chdir=terraform fmt -check
.tools/terraform -chdir=terraform validate
echo '[7/7] Generating the Azure resource plan...'
.tools/terraform -chdir=terraform plan -input=false -var-file=coursework.auto-inputs.tfvars.json -out=coursework.tfplan
echo 'Plan only: no resources created. Keep Terraform state and the SSH private key in persistent storage.'
echo 'Review the plan, student quota, VM availability and cost before terraform apply coursework.tfplan.'
