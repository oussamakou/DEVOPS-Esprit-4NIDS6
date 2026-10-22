"""Scan Git's staged snapshot. CI separately scans the full history."""
from pathlib import Path
import os
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
binary = root / ".tools" / ("gitleaks.exe" if os.name == "nt" else "gitleaks")
if not binary.is_file():
    raise SystemExit("Install the pinned scanner first: python scripts/install-tools.py gitleaks")
sys.exit(subprocess.call([str(binary), "git", "--pre-commit", "--staged", "--redact", "--no-banner"], cwd=root))
