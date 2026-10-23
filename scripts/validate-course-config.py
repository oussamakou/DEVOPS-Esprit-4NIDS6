"""Validate both Compose graphs without contacting a Docker daemon or real service."""
import os
from pathlib import Path
import subprocess

import yaml

root = Path(__file__).resolve().parents[1]

# A valid Compose schema can still produce no host port mappings on internal
# networks. Catch the topology that broke the first live Azure deployment.
runtime = yaml.safe_load((root / "cloud/runtime/compose.yml").read_text(encoding="utf-8"))
for name, service in runtime["services"].items():
    if service.get("ports"):
        if all(runtime["networks"][network].get("internal", False) for network in service["networks"]):
            raise SystemExit(f"{name}: published ports need a non-internal bridge network")
        if any(not port.startswith("127.0.0.1:") for port in service["ports"]):
            raise SystemExit(f"{name}: lab ports must bind to localhost for SSH access")
if runtime["services"]["mysql"].get("ports") or any(
    not runtime["networks"][network].get("internal", False)
    for network in runtime["services"]["mysql"]["networks"]
):
    raise SystemExit("MySQL must stay unpublished on internal networks")
environment = dict(os.environ, MYSQL_ROOT_PASSWORD="validation-only", DB_PASSWORD="validation-only",
                   GRAFANA_PASSWORD="validation-only", SONAR_DB_PASSWORD="validation-only",
                   APP_IMAGE="testregistry.azurecr.io/student-management@sha256:" + "a" * 64)
for name in ("runtime", "tools"):
    subprocess.run(["docker", "compose", "-f", str(root / f"cloud/{name}/compose.yml"),
                    "--profile", "https", "config", "--quiet"], env=environment, check=True)
print("Validated Azure tools and runtime Compose configuration (no containers started).")
