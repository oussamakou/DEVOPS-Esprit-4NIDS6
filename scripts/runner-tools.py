"""Start and configure the disposable SonarQube and Nexus for the GitHub-runner lane.

Uses cloud/tools/compose.yml unchanged (same versions as the Azure tools VM; the
Caddy HTTPS profile is not started). Ports stay on 127.0.0.1 inside a runner that
is destroyed after the job.

  start                   generate .env and the Nexus key, start postgres/sonarqube/nexus
  sonar-setup  REPORT_DIR wait for SonarQube, set SONAR_ADMIN_PASSWORD, create the project and token
  nexus-setup  REPORT_DIR wait for Nexus, set NEXUS_ADMIN_PASSWORD, accept the EULA, check maven-snapshots
  stop                    stop the tools to free memory for the deployment

Secrets come from the environment and are never printed: this script runs under
capture-check.py, whose log becomes a published report. The SonarQube analysis
token is written to a 0600 file for the workflow to mask and export.
"""
import base64
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".tools/runner-tools"
SONAR = "http://127.0.0.1:9000"
NEXUS = "http://127.0.0.1:8081"
PROJECT = "student-management"


def request(method, url, auth=None, data=None, json_body=None, content_type=None, timeout=30):
    headers = {"User-Agent": "student-devsecops-runner"}
    if auth:
        headers["Authorization"] = "Basic " + base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
    body = None
    if json_body is not None:
        body, headers["Content-Type"] = json.dumps(json_body).encode(), "application/json"
    elif data is not None:
        body = data.encode() if isinstance(data, str) else urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = content_type or "application/x-www-form-urlencoded"
    with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers, method=method), timeout=timeout) as response:
        raw = response.read()
        return response.status, (json.loads(raw) if raw and raw[:1] in b"[{" else raw.decode(errors="replace"))


def wait_for(name, probe, timeout=900, every=10):
    started = time.time()
    while time.time() - started < timeout:
        try:
            if probe():
                print(f"{name} ready after {int(time.time() - started)} s")
                return
        except (urllib.error.URLError, OSError, ValueError, KeyError, subprocess.CalledProcessError):
            pass
        time.sleep(every)
    raise SystemExit(f"{name} did not become ready within {timeout} s")


def secret(name):
    value = os.environ.get(name, "")
    if len(value) < 16:
        raise SystemExit(f"{name} must be set (generated and masked by the workflow)")
    return value


def compose(*args, capture=False):
    command = ["docker", "compose", "--project-directory", str(WORK), "-f", str(WORK / "compose.yml"), *args]
    return subprocess.run(command, check=True, capture_output=capture, text=True)


def start():
    WORK.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "cloud/tools/compose.yml", WORK / "compose.yml")
    env = WORK / ".env"
    env.write_text(f"SONAR_DB_PASSWORD={secrets.token_hex(32)}\n", encoding="utf-8")
    env.chmod(0o600)
    key = WORK / "nexus-secrets.json"
    key.write_text(json.dumps({"active": "runner-v1", "keys": [{"id": "runner-v1", "key": base64.b64encode(secrets.token_bytes(32)).decode()}]}) + "\n")
    # Same ownership and mode as on the Azure tools VM: the Nexus container runs as UID/GID 200.
    subprocess.run(["sudo", "chown", "200:200", str(key)], check=True)
    subprocess.run(["sudo", "chmod", "400", str(key)], check=True)
    # SonarQube's embedded Elasticsearch needs these kernel limits.
    subprocess.run(["sudo", "sysctl", "-w", "vm.max_map_count=524288", "fs.file-max=131072"], check=True)
    compose("up", "-d", "postgres", "sonarqube", "nexus")
    print("SonarQube and Nexus starting on 127.0.0.1:9000 and 127.0.0.1:8081 (Caddy HTTPS profile not started)")


def sonar_setup(report_dir):
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    wait_for("SonarQube", lambda: request("GET", SONAR + "/api/system/status")[1].get("status") == "UP")
    password = secret("SONAR_ADMIN_PASSWORD")
    request("POST", SONAR + "/api/users/change_password", auth=("admin", "admin"),
            data={"login": "admin", "previousPassword": "admin", "password": password})
    admin = ("admin", password)
    request("POST", SONAR + "/api/projects/create", auth=admin, data={"project": PROJECT, "name": PROJECT})
    _, token = request("POST", SONAR + "/api/user_tokens/generate", auth=admin,
                       data={"name": f"ci-{os.environ.get('GITHUB_RUN_ID', 'local')}", "type": "PROJECT_ANALYSIS_TOKEN", "projectKey": PROJECT})
    token_file = WORK / "sonar-token"
    token_file.write_text(token["token"], encoding="utf-8")
    token_file.chmod(0o600)
    # Read-only anonymous browsing, only inside this disposable runner, so the UI can be screenshot.
    request("POST", SONAR + "/api/settings/set", auth=admin, data={"key": "sonar.forceAuthentication", "value": "false"})
    _, version = request("GET", SONAR + "/api/server/version")
    facts = {"server": SONAR, "version": str(version).strip(), "project": PROJECT,
             "admin_password": "replaced with a random per-run value", "anonymous_read": "enabled (disposable runner only)"}
    (report_dir / "sonar-setup-facts.json").write_text(json.dumps({"stage": "sonar-setup", "facts": facts}, indent=2) + "\n")
    print(f"SonarQube {facts['version']} ready: project {PROJECT} created, analysis token issued")


def nexus_setup(report_dir):
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    wait_for("Nexus", lambda: request("GET", NEXUS + "/service/rest/v1/status/writable")[0] == 200)
    wait_for("Nexus initial password", lambda: compose("exec", "-T", "nexus", "test", "-s", "/nexus-data/admin.password", capture=True) is not None, every=5)
    initial = compose("exec", "-T", "nexus", "cat", "/nexus-data/admin.password", capture=True).stdout.strip()
    password = secret("NEXUS_ADMIN_PASSWORD")
    request("PUT", NEXUS + "/service/rest/v1/security/users/admin/change-password", auth=("admin", initial),
            data=password, content_type="text/plain")
    admin = ("admin", password)
    # Community Edition blocks uploads until its EULA is accepted. The owner chose automatic
    # acceptance for these disposable instances; the exact disclaimer accepted is kept as evidence.
    _, eula = request("GET", NEXUS + "/service/rest/v1/system/eula", auth=admin)
    if not eula.get("accepted"):
        request("POST", NEXUS + "/service/rest/v1/system/eula", auth=admin, json_body={"accepted": True, "disclaimer": eula["disclaimer"]})
    _, after = request("GET", NEXUS + "/service/rest/v1/system/eula", auth=admin)
    if not after.get("accepted"):
        raise SystemExit("Nexus EULA acceptance was not recorded")
    (report_dir / "nexus-eula-accepted.json").write_text(json.dumps(after, indent=2) + "\n")
    # Read-only anonymous browsing, only inside this disposable runner, so the UI can be screenshot.
    request("PUT", NEXUS + "/service/rest/v1/security/anonymous", auth=admin,
            json_body={"enabled": True, "userId": "anonymous", "realmName": "NexusAuthorizingRealm"})
    _, repositories = request("GET", NEXUS + "/service/rest/v1/repositories", auth=admin)
    if not any(r.get("name") == "maven-snapshots" and r.get("format") == "maven2" for r in repositories):
        raise SystemExit("Nexus has no maven-snapshots repository")
    facts = {"server": NEXUS, "repository": "maven-snapshots", "eula": "accepted (disclaimer saved)",
             "admin_password": "replaced with a random per-run value", "anonymous_read": "enabled (disposable runner only)"}
    (report_dir / "nexus-setup-facts.json").write_text(json.dumps({"stage": "nexus-setup", "facts": facts}, indent=2) + "\n")
    print("Nexus ready: admin password replaced, EULA accepted, maven-snapshots present")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action == "start":
        start()
    elif action == "sonar-setup" and len(sys.argv) == 3:
        sonar_setup(sys.argv[2])
    elif action == "nexus-setup" and len(sys.argv) == 3:
        nexus_setup(sys.argv[2])
    elif action == "stop":
        compose("stop")
        print("SonarQube, PostgreSQL and Nexus stopped to free memory for the deployment")
    else:
        raise SystemExit(__doc__)
