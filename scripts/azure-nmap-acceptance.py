"""Use existing VM-scoped Azure Run Command rights; return every original report."""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def run_command(resource_group, vm, script, scratch):
    path = scratch / "guest-command.sh"
    path.write_text(script, encoding="utf-8", newline="\n")
    completed = subprocess.run(["az", "vm", "run-command", "invoke", "--resource-group", resource_group,
                                "--name", vm, "--command-id", "RunShellScript", "--scripts", "@" + str(path),
                                "--output", "json"], capture_output=True, text=True, timeout=900)
    if completed.returncode != 0:
        raise RuntimeError("Azure Run Command failed: " + completed.stderr[-1500:])
    data = json.loads(completed.stdout)
    lines = [line for item in data.get("value", []) for line in item.get("message", "").splitlines() if line.startswith("NMAP_REPORT_V1 ")]
    if len(lines) != 1:
        raise RuntimeError("Guest scan did not return one complete report marker; scan/install may have failed")
    return json.loads(lines[0].split(" ", 1)[1])


def unpack_reports(payload, output):
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        files = archive.infolist()
        if not 1 <= len(files) <= 50 or sum(p.file_size for p in files) > 20 * 1024 * 1024:
            raise ValueError("Invalid report archive size")
        if len({p.filename for p in files}) != len(files):
            raise ValueError("Duplicate report archive names")
        for member in files:
            if not re.fullmatch(r"[a-z]+(?:-[a-z]+)*\.(?:xml|nmap|gnmap|log|json|txt)", member.filename):
                raise ValueError("Unexpected report archive path")
        for member in files:
            (output / member.filename).write_bytes(archive.read(member))


def collect(resource_group, vm, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    try:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in ("security/nmap-policy.json", "scripts/nmap-acceptance.py", "scripts/nmap-vm-probe.py"):
                archive.writestr(name, (ROOT / name).read_bytes())
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        script = '''#!/bin/bash
set -euo pipefail
umask 077
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
'''
        script += f"printf '%s' '{encoded}' | base64 -d > \"$work/probe.zip\"\n"
        script += '''python3 -c 'import sys,zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' "$work/probe.zip" "$work"
if ! command -v nmap >/dev/null; then
  if ! (apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends nmap) >"$work/nmap-install.log" 2>&1; then
    echo 'Nmap installation failed on the application VM.' >&2
    tail -n 3 "$work/nmap-install.log" >&2
    exit 1
  fi
fi
python3 "$work/scripts/nmap-vm-probe.py" scan
'''
        with tempfile.TemporaryDirectory() as folder:
            scratch = Path(folder)
            first = run_command(resource_group, vm, script, scratch)
            identifier, count, digest = first["id"], first["chunks"], first["sha256"]
            if not re.fullmatch(r"[a-f0-9]{32}", identifier) or not isinstance(count, int) or not 1 <= count <= 100 or not re.fullmatch(r"[a-f0-9]{64}", digest) or first["index"] != 0:
                raise ValueError("Invalid guest report manifest")
            chunks = [first["payload"]]
            for index in range(1, count):
                item = run_command(resource_group, vm, f"set -eu\npython3 /opt/student-course/acceptance/nmap/fetch-reports.py fetch {identifier} {index}\n", scratch)
                if any(item[key] != value for key, value in {"id": identifier, "chunks": count, "sha256": digest, "index": index}.items()):
                    raise ValueError("Guest report chunk identity mismatch")
                chunks.append(item["payload"])
            payload = base64.b64decode(''.join(chunks), validate=True)
            if hashlib.sha256(payload).hexdigest() != digest:
                raise ValueError("Guest report checksum mismatch")
            unpack_reports(payload, output)
            (output / "azure-transport.json").write_text(json.dumps({"report_id": identifier, "chunks": count, "sha256": digest, "vm": vm}, indent=2) + '\n', encoding='utf-8')
        result = json.loads((output / "result.json").read_text(encoding="utf-8"))
        print(f"NMAP_ACCEPTANCE private: {result['status']} ({count} verified report chunks)")
        for item in result.get("profiles", []):
            print(f"  {item['name']}: {item['status']}, open={item.get('open_ports', [])}")
        return result["status"] == "passed"
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        (output / "result.json").write_text(json.dumps({"view": "private", "status": "error", "profiles": [], "error": str(error)}, indent=2) + '\n', encoding='utf-8')
        print("NMAP_ACCEPTANCE private: ERROR: " + str(error))
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource-group", default=os.environ.get("AZURE_RESOURCE_GROUP"), required=not bool(os.environ.get("AZURE_RESOURCE_GROUP")))
    parser.add_argument("--vm", default=os.environ.get("AZURE_VM_NAME"), required=not bool(os.environ.get("AZURE_VM_NAME")))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    raise SystemExit(0 if collect(args.resource_group, args.vm, args.output) else 1)
