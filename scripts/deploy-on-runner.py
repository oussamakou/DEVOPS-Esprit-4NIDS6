"""Deploy the scanned image on the disposable GitHub runner with the lab's own Compose definition.

  deploy  IMAGE  assemble .tools/runner-runtime from cloud/runtime and the provisioned dashboards,
                 generate private passwords, start the stack, start Node Exporter on the private
                 Docker bridge address, and verify a database-backed API request and the running digest
  smoke   IMAGE  recheck the deployed digest and database-backed API after network acceptance
  monitor IMAGE  verify Prometheus scrapes the API and the runner exporter (UP) and Grafana is healthy

IMAGE must be the immutable digest pushed to the runner's local registry. Like the Azure
guest script (compose-on-vm.sh), deployment emits a DEPLOY_SUCCEEDED marker.
The smoke test emits PRODUCTION_SMOKE_PASSED after both checks succeed.
"""
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".tools/runner-runtime"
IMAGE = re.compile(r"(localhost|127\.0\.0\.1):5000/student-management@sha256:[a-f0-9]{64}")
OVERRIDES = {"services": {"grafana": {"environment": {
    # Read-only anonymous viewing, only in this disposable runner, so dashboards can be screenshot.
    "GF_AUTH_ANONYMOUS_ENABLED": "true", "GF_AUTH_ANONYMOUS_ORG_ROLE": "Viewer"}}}}


def compose(*args, capture=False):
    command = ["docker", "compose", "--project-directory", str(RUNTIME), "-f", str(RUNTIME / "compose.yml"),
               "-f", str(RUNTIME / "runner-overrides.yml"), *args]
    return subprocess.run(command, check=True, capture_output=capture, text=True)


def get_json(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.load(response)


def poll(description, check, attempts=60, pause=3):
    for _ in range(attempts):
        try:
            if check():
                return True
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            pass
        time.sleep(pause)
    print(f"{description} FAILED", file=sys.stderr)
    subprocess.run(["docker", "compose", "--project-directory", str(RUNTIME), "-f", str(RUNTIME / "compose.yml"), "ps", "-a"], check=False)
    return False


def assemble(image):
    RUNTIME.mkdir(parents=True, exist_ok=True)
    for path in (ROOT / "cloud/runtime").glob("*.yml"):
        shutil.copy(path, RUNTIME / path.name)
    shutil.copy(ROOT / "cloud/runtime/vms.json", RUNTIME / "vms.json")
    dashboard = next(yaml.safe_load_all((ROOT / "monitoring/dashboard.yaml").read_text(encoding="utf-8")))
    (RUNTIME / "student.json").write_text(dashboard["data"]["student.json"], encoding="utf-8")
    (RUNTIME / "runner-overrides.yml").write_text(yaml.safe_dump(OVERRIDES), encoding="utf-8")
    (RUNTIME / "node-targets").mkdir(exist_ok=True)
    env = RUNTIME / ".env"
    env.write_text("".join(f"{name}={secrets.token_hex(32)}\n" for name in ("MYSQL_ROOT_PASSWORD", "DB_PASSWORD", "GRAFANA_PASSWORD"))
                   + f"APP_IMAGE={image}\n", encoding="utf-8")
    env.chmod(0o600)


def deploy(image):
    assemble(image)
    compose("up", "-d", "--wait", "--wait-timeout", "300")
    gateway = subprocess.run(["docker", "network", "inspect", "student-course_host_access", "--format",
                              "{{(index .IPAM.Config 0).Gateway}}"], check=True, capture_output=True, text=True).stdout.strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", gateway):
        raise SystemExit("Could not find the private Docker bridge address for Node Exporter")
    subprocess.run(["docker", "compose", "-f", str(ROOT / "cloud/node-exporter/compose.yml"), "up", "-d"], check=True,
                   env={**os.environ, "NODE_EXPORTER_PRIVATE_IP": gateway})
    targets = [{"targets": [f"{gateway}:9100"], "labels": {"host": "github-runner", "role": "disposable-runner"}}]
    (RUNTIME / "node-targets/runner.json").write_text(json.dumps(targets, indent=2) + "\n", encoding="utf-8")
    print(f"Node Exporter listening on the private Docker bridge address {gateway}:9100 (not on the runner's network interface)")
    verify_deployment(image)
    print(f"DEPLOY_SUCCEEDED compose-deploy {image}")


def verify_deployment(image):
    if not poll("API_READINESS", lambda: isinstance(get_json("http://127.0.0.1:8089/student/students/getAllStudents"), list)):
        raise SystemExit("API_READINESS_FAILED: 127.0.0.1:8089 did not return a database-backed JSON array")
    container = compose("ps", "-q", "app", capture=True).stdout.strip()
    running = subprocess.run(["docker", "inspect", "--format", "{{.Config.Image}}", container], check=True,
                             capture_output=True, text=True).stdout.strip()
    if running != image:
        raise SystemExit(f"Running image {running} is not the scanned digest")
    print("API returned a database-backed JSON array; the running container uses the scanned digest")


def smoke(image):
    verify_deployment(image)
    print(f"PRODUCTION_SMOKE_PASSED {image}")


def monitor(image):
    expected = sum(len(group["targets"]) for path in (RUNTIME / "node-targets").glob("*.json")
                   for group in json.loads(path.read_text(encoding="utf-8")))

    def healthy():
        targets = get_json("http://127.0.0.1:9091/api/v1/targets")["data"]["activeTargets"]
        api = any(t["labels"].get("job") == "student-api" and t["health"] == "up" for t in targets)
        nodes = [t for t in targets if t["labels"].get("job") == "azure-nodes"]
        return api and len(nodes) == expected and all(t["health"] == "up" for t in nodes) \
            and get_json("http://127.0.0.1:3000/api/health").get("database") == "ok"
    if not poll("MONITORING", healthy, attempts=40):
        raise SystemExit("MONITORING_FAILED: API or runner scrape target or Grafana database is not healthy")
    print(f"MONITORING_VERIFIED: API and {expected} runner exporter target(s) UP; Grafana database ok")
    print(f"DEPLOY_SUCCEEDED compose-monitor {image}")


if __name__ == "__main__":
    commands = {"deploy": deploy, "smoke": smoke, "monitor": monitor}
    if len(sys.argv) != 3 or sys.argv[1] not in commands or not IMAGE.fullmatch(sys.argv[2]):
        raise SystemExit(__doc__)
    commands[sys.argv[1]](sys.argv[2])
