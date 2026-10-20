"""Emit a self-contained Run Command script from trusted repository files."""
import base64
import io
from pathlib import Path
import re
import sys
import tarfile

root = Path(__file__).resolve().parents[1]
image = sys.argv[1]
if not re.fullmatch(r"[a-z0-9]+\.azurecr\.io/student-management@sha256:[a-f0-9]{64}", image):
    raise SystemExit("Expected an immutable Azure registry image digest")
buffer = io.BytesIO()
with tarfile.open(fileobj=buffer, mode="w:gz") as bundle:
    for folder in ("k8s", "monitoring"):
        for file in sorted((root / folder).glob("*.yaml")):
            data = file.read_text(encoding="utf-8").replace("IMAGE_PLACEHOLDER", image).encode()
            info = tarfile.TarInfo(f"{folder}/{file.name}")
            info.size = len(data)
            info.mode = 0o600
            bundle.addfile(info, io.BytesIO(data))
    for name in ("deploy-on-vm.sh", "refresh-acr-secret.sh"):
        data = (root / "scripts" / name).read_bytes().replace(b"\r\n", b"\n")
        info = tarfile.TarInfo(name)
        info.size = len(data)
        info.mode = 0o700
        bundle.addfile(info, io.BytesIO(data))
encoded = base64.b64encode(buffer.getvalue()).decode()
print("#!/bin/bash\nset -euo pipefail\numask 077")
print('work=$(mktemp -d)\ntrap \'rm -rf "$work"\' EXIT')
print(f"printf '%s' '{encoded}' | base64 -d | tar -xz -C \"$work\"")
print(f"bash \"$work/deploy-on-vm.sh\" \"$work\" '{image}'")
