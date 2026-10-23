"""Generate an isolated, explicitly labelled fixture and run a real blocking tool.

No vulnerable application code or working credentials are saved in the repository.
The command intentionally exits 1 when the requested finding is detected; a scanner
error or missing expected finding exits 2. CI preserves the report for screenshots.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("kind", choices=["secret", "sast", "hook"])
parser.add_argument("--report-dir", default=".tools/exercise")
args = parser.parse_args()
reports = Path(args.report_dir).resolve()
reports.mkdir(parents=True, exist_ok=True)
print(f"CONTROLLED EXERCISE: {args.kind}. This is a temporary fixture, not an application incident.", flush=True)
with tempfile.TemporaryDirectory(prefix="devsecops-exercise-") as directory:
    folder = Path(directory)
    if args.kind == "secret":
        # Syntactically recognisable but deliberately fake; never contacts a provider.
        (folder / "demo.env").write_text('GITHUB_TOKEN=ghp_' + 'A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8' + '\n')
        binary = ROOT / ".tools" / ("gitleaks.exe" if os.name == "nt" else "gitleaks")
        report = reports / "secret.json"
        command = [str(binary), "dir", str(folder), "--redact", "--no-banner", "--report-format", "json", "--report-path", str(report)]
    elif args.kind == "sast":
        (folder / "CommandDemo.java").write_text('class CommandDemo { void run(String input) throws Exception { Runtime.getRuntime().exec(input); } }\n')
        report = reports / "sast.json"
        command = ["semgrep", "scan", "--config", str(ROOT / ".semgrep"), "--error", "--strict", "--metrics=off", "--no-git-ignore", "--json-output", str(report), str(folder)]
    else:
        fixture = folder / "broken.yaml"
        fixture.write_text('service: [unclosed\n')
        report = reports / "hook.txt"
        command = [sys.executable, str(ROOT / "scripts/check-files.py"), str(fixture)]
    try:
        result = subprocess.run(command, capture_output=True, text=True)
    except OSError:
        print("EXERCISE_INVALID: scanner could not start; install the pinned tool first.")
        sys.exit(2)
    output = result.stdout + result.stderr
    (reports / f"{args.kind}.log").write_text(output, encoding="utf-8")
    print(output, flush=True)
    detected = result.returncode == 1
    if args.kind in ("secret", "sast"):
        if not report.is_file():
            detected = False
        else:
            try:
                data = json.loads(report.read_text(encoding="utf-8"))
                if args.kind == "secret":
                    finding = any(item.get("RuleID") == "github-pat" for item in data)
                else:
                    finding = any(item.get("check_id", "").endswith("java-runtime-command-execution") for item in data.get("results", []))
                detected = detected and finding
            except (ValueError, TypeError, AttributeError):
                detected = False
    else:
        report.write_text(output, encoding="utf-8")
        detected = detected and "FAIL" in output
    if not detected:
        print("EXERCISE_INVALID: scanner failed unexpectedly or the intended finding was absent.")
        sys.exit(2)
    print("EXERCISE_BLOCKED_AS_EXPECTED: capture this finding; then show a separate clean application scan.")
    sys.exit(1)
