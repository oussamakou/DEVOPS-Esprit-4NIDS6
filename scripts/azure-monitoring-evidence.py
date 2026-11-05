"""Collect real Prometheus and Grafana evidence from the Azure app VM.

Uses the same VM-scoped Run Command permission as the deployment (no SSH, no new
port, no new role). The guest returns a zip in checksummed chunks because Azure
keeps only the last ~4 KB of output; this script reassembles and verifies it,
then writes prometheus/ and grafana/ evidence into the report tree. It exits
non-zero when transport fails or a required monitoring check is not satisfied.

Usage: python scripts/azure-monitoring-evidence.py --output .tools/reports
"""
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
MARKER = "MONITORING_EVIDENCE_V1 "
FETCH = "/opt/student-course/evidence/monitoring/fetch-evidence.py"


def run_command(resource_group, vm, script, scratch):
    path = scratch / "guest-command.sh"
    path.write_text(script, encoding="utf-8", newline="\n")
    completed = subprocess.run(["az", "vm", "run-command", "invoke", "--resource-group", resource_group,
                                "--name", vm, "--command-id", "RunShellScript", "--scripts", "@" + str(path),
                                "--output", "json"], capture_output=True, text=True, timeout=900)
    if completed.returncode != 0:
        raise RuntimeError("Azure Run Command failed: " + completed.stderr[-1500:])
    data = json.loads(completed.stdout)
    lines = [line for item in data.get("value", []) for line in item.get("message", "").splitlines() if line.startswith(MARKER)]
    if len(lines) != 1:
        raise RuntimeError("Guest collector did not return one complete evidence marker; it may have failed")
    return json.loads(lines[0][len(MARKER):])


def reassemble(first, fetch):
    """Validate the manifest and chunks; `fetch(index)` returns the next chunk manifest."""
    identifier, count, digest = first["id"], first["chunks"], first["sha256"]
    if (not re.fullmatch(r"[a-f0-9]{32}", identifier) or not isinstance(count, int) or not 1 <= count <= 100
            or not re.fullmatch(r"[a-f0-9]{64}", digest) or first["index"] != 0):
        raise ValueError("Invalid guest evidence manifest")
    chunks = [first["payload"]]
    for index in range(1, count):
        item = fetch(identifier, index)
        if any(item[key] != value for key, value in {"id": identifier, "chunks": count, "sha256": digest, "index": index}.items()):
            raise ValueError("Guest evidence chunk identity mismatch")
        chunks.append(item["payload"])
    payload = base64.b64decode("".join(chunks), validate=True)
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError("Guest evidence checksum mismatch")
    return payload, identifier, count, digest


def unpack(payload):
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = archive.infolist()
        if [m.filename for m in members] != ["evidence.json"] or members[0].file_size > 5 * 1024 * 1024:
            raise ValueError("Unexpected evidence archive contents")
        return json.loads(archive.read("evidence.json"))


def write_reports(evidence, output):
    """Split the evidence into prometheus/ and grafana/ and return the failed required checks."""
    output = Path(output)
    (output / "prometheus").mkdir(parents=True, exist_ok=True)
    (output / "grafana").mkdir(parents=True, exist_ok=True)
    checks = evidence["checks"]
    prometheus = {"generated_utc": evidence["generated_utc"], "traffic": evidence["traffic"],
                  "prometheus": {k: v for k, v in evidence["prometheus"].items() if k != "ranges"},
                  "checks": [c for c in checks if c["name"].startswith("Prometheus")]}
    grafana = {"generated_utc": evidence["generated_utc"], "grafana": evidence["grafana"],
               "panel_data": evidence["prometheus"]["ranges"],
               "checks": [c for c in checks if c["name"].startswith("Grafana")]}
    (output / "prometheus/prometheus-evidence.json").write_text(json.dumps(prometheus, indent=2) + "\n", encoding="utf-8")
    (output / "grafana/grafana-evidence.json").write_text(json.dumps(grafana, indent=2) + "\n", encoding="utf-8")
    return [c for c in checks if c["required"] and not c["ok"]]


def collect(resource_group, vm, output):
    script_text = (ROOT / "scripts/monitoring-vm-evidence.py").read_bytes()
    encoded = base64.b64encode(script_text).decode("ascii")
    script = ("#!/bin/bash\nset -euo pipefail\numask 077\nwork=$(mktemp -d)\ntrap 'rm -rf \"$work\"' EXIT\n"
              f"printf '%s' '{encoded}' | base64 -d > \"$work/monitoring-vm-evidence.py\"\n"
              "python3 \"$work/monitoring-vm-evidence.py\" collect\n")
    with tempfile.TemporaryDirectory() as folder:
        scratch = Path(folder)
        first = run_command(resource_group, vm, script, scratch)
        payload, identifier, count, digest = reassemble(
            first, lambda ident, index: run_command(resource_group, vm, f"set -eu\npython3 {FETCH} fetch {ident} {index}\n", scratch))
    evidence = unpack(payload)
    failed = write_reports(evidence, output)
    for check in evidence["checks"]:
        print(f"{'PASS' if check['ok'] else 'FAIL'}{'' if check['required'] else ' (informational)'}: {check['name']} - {check['detail']}")
    print(f"MONITORING_EVIDENCE: {count} verified chunk(s), sha256 {digest[:16]}..., report id {identifier}")
    if failed:
        raise SystemExit("Required monitoring checks failed: " + "; ".join(c["name"] for c in failed))
    print("MONITORING_EVIDENCE_VERIFIED: Prometheus and Grafana evidence collected")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource-group", default=os.environ.get("AZURE_RESOURCE_GROUP"), required=not bool(os.environ.get("AZURE_RESOURCE_GROUP")))
    parser.add_argument("--vm", default=os.environ.get("AZURE_VM_NAME"), required=not bool(os.environ.get("AZURE_VM_NAME")))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    collect(args.resource_group, args.vm, args.output)
