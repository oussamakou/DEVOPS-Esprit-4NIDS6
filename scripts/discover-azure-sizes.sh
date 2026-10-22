#!/bin/bash
# Read-only candidate discovery; never changes Terraform inputs or deploys resources.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
python3 -u scripts/check-azure-skus.py --report-only "${1:-francecentral}" \
  Standard_B2s Standard_B2als_v2 Standard_B2s_v2 Standard_D2s_v4 Standard_D2as_v4 \
  Standard_D4s_v4 Standard_D4s_v3 Standard_D4as_v4 Standard_B4s_v2 Standard_B4as_v2
