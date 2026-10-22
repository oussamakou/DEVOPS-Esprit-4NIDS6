"""Package tracked Compose configuration for an Azure control-plane deployment."""
import base64
import io
from pathlib import Path
import re
import sys
import tarfile

import yaml

root = Path(__file__).resolve().parents[1]
mode, image = sys.argv[1:]
if mode not in ("deploy", "monitor") or not re.fullmatch(r"[a-z0-9]+\.azurecr\.io/student-management@sha256:[a-f0-9]{64}", image):
    raise SystemExit("Expected deploy/monitor and an immutable ACR digest")
files = {f"runtime/{p.name}": p.read_bytes() for p in (root / "cloud/runtime").glob("*.yml")}
dashboard = next(yaml.safe_load_all((root / "monitoring/dashboard.yaml").read_text(encoding="utf-8")))
files["runtime/student.json"] = dashboard["data"]["student.json"].encode()
files["compose-on-vm.sh"] = (root / "scripts/compose-on-vm.sh").read_bytes().replace(b"\r\n", b"\n")
buffer = io.BytesIO()
with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
    for name, data in files.items():
        info = tarfile.TarInfo(name)
        info.size = len(data)
        info.mode = 0o600
        archive.addfile(info, io.BytesIO(data))
encoded = base64.b64encode(buffer.getvalue()).decode()
print('#!/bin/bash\nset -euo pipefail\numask 077\nwork=$(mktemp -d)\ntrap \'rm -rf "$work"\' EXIT')
print(f"printf '%s' '{encoded}' | base64 -d | tar -xz -C \"$work\"")
print(f'bash "$work/compose-on-vm.sh" {mode} "$work" \'{image}\'')
