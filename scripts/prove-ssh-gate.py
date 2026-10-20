"""Run a deliberately insecure fixture through Checkov; never applies cloud resources.

Usage: python scripts/prove-ssh-gate.py path/to/checkov-launcher
On Windows, supply .tools/venv/Scripts/checkov (the Python script, without .cmd).
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

fixture = '''resource "azurerm_network_security_rule" "insecure_demo" {
  name = "demo-only-do-not-apply"
  priority = 100
  direction = "Inbound"
  access = "Allow"
  protocol = "Tcp"
  source_port_range = "*"
  destination_port_range = "22"
  source_address_prefix = "0.0.0.0/0"
  destination_address_prefix = "*"
  resource_group_name = "not-created"
  network_security_group_name = "not-created"
}
'''
with tempfile.TemporaryDirectory(prefix="student-ssh-gate-") as folder:
    path = Path(folder) / "insecure.tf"
    path.write_text(fixture, encoding="utf-8")
    command = [sys.executable, str(Path(sys.argv[1]).resolve())] if len(sys.argv) > 1 else ["checkov"]
    # Run outside the repo so the regular project's configuration does not affect the fixture.
    custom = str(Path(__file__).resolve().parents[1] / "checkov_checks")
    result = subprocess.run(command + ["--file", str(path), "--framework", "terraform", "--external-checks-dir", custom, "--check", "CKV_LAB_1", "-o", "json"],
                            cwd=folder, capture_output=True, text=True)
    if result.returncode != 1:
        raise SystemExit(f"Expected a policy failure (1), received {result.returncode}: {result.stderr} {result.stdout}")
    report = json.loads(result.stdout)
    failures = report["results"]["failed_checks"]
    if not any(check["check_id"] == "CKV_LAB_1" for check in failures):
        raise SystemExit("Checkov did not report the intended SSH failure")
    print("PASS: Checkov blocked internet-wide SSH in an isolated fixture. No cloud resources were created.")
