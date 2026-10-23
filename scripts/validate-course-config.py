"""Validate both Compose graphs without contacting a Docker daemon or real service."""
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
environment = dict(os.environ, MYSQL_ROOT_PASSWORD="validation-only", DB_PASSWORD="validation-only",
                   GRAFANA_PASSWORD="validation-only", SONAR_DB_PASSWORD="validation-only",
                   APP_IMAGE="testregistry.azurecr.io/student-management@sha256:" + "a" * 64)
for name in ("runtime", "tools"):
    subprocess.run(["docker", "compose", "-f", str(root / f"cloud/{name}/compose.yml"),
                    "--profile", "https", "config", "--quiet"], env=environment, check=True)
print("Validated Azure tools and runtime Compose configuration (no containers started).")
