"""Offline structural checks. Terraform/scanner/schema/runtime checks remain separate."""
import ast
import json
from pathlib import Path
import subprocess
import sys
import yaml

root = Path(__file__).resolve().parents[1]
for path in (root / "scripts").glob("*.py"):
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
resources = []
for folder in ("k8s", "monitoring"):
    for path in (root / folder).glob("*.yaml"):
        for resource in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            assert resource["apiVersion"] and resource["kind"] and resource["metadata"]["name"], path
            if resource["kind"] != "Namespace":
                assert resource["metadata"].get("namespace") == "student", path
            resources.append(resource)
identities = [(r["kind"], r["metadata"]["name"]) for r in resources]
assert len(identities) == len(set(identities)), "Duplicate resource identity"
assert not any(r["kind"] == "Secret" for r in resources), "Credentials must not be versioned"
dashboard = next(r for r in resources if r["metadata"]["name"] == "student-dashboard")
json.loads(dashboard["data"]["student.json"])
image = "studentregistry.azurecr.io/student-management@sha256:" + "a" * 64
bundle = subprocess.check_output([sys.executable, str(root / "scripts" / "make-deploy-bundle.py"), image], text=True)
assert "DEPLOY_SUCCEEDED" not in bundle, "Marker must only be emitted after remote checks"
assert "set -euo pipefail" in bundle
print(f"Parsed Python scripts, dashboard JSON and {len(resources)} Kubernetes resources; deployment bundle generated.")
