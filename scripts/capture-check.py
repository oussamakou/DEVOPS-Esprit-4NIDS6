"""Run a check, preserve its real exit status and collect readable CI evidence."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys


def capture(name, output, command):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    folder = Path(output)
    folder.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    with (folder / f"{name}.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", errors="replace")
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)
        code = process.wait()
    result = {"check": name, "command": command, "exit_code": code,
              "status": "passed" if code == 0 else "failed", "started_utc": started,
              "finished_utc": datetime.now(timezone.utc).isoformat(),
              "commit": os.environ.get("GITHUB_SHA", "local"),
              "run_url": (f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
                          if os.environ.get("GITHUB_RUN_ID") else None)}
    (folder / f"{name}-result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"CHECK_RESULT: {name} {result['status']} (exit {code})")
    return code


if __name__ == "__main__":
    name, output, *command = sys.argv[1:]
    if command and command[0] == "--":
        command.pop(0)
    if not command or not name.replace("-", "").isalnum():
        raise SystemExit("Expected safe check name, report directory and command")
    sys.exit(capture(name, output, command))
