"""Collect Prometheus and Grafana evidence on the disposable runner, reusing the Azure collector.

Runs scripts/monitoring-vm-evidence.py's collect() directly (no Run Command transport
is needed on the runner) and writes the same prometheus/ and grafana/ report files with
azure-monitoring-evidence.py's write_reports(). Exits non-zero when a required check fails.

Usage: python scripts/runner-monitoring-evidence.py REPORT_ROOT
"""
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    collector = load("collector", "monitoring-vm-evidence.py")
    writer = load("writer", "azure-monitoring-evidence.py")
    evidence = collector.collect(env_file=ROOT / ".tools/runner-runtime/.env")
    failed = writer.write_reports(evidence, sys.argv[1])
    for check in evidence["checks"]:
        print(f"{'PASS' if check['ok'] else 'FAIL'}{'' if check['required'] else ' (informational)'}: {check['name']} - {check['detail']}")
    if failed:
        raise SystemExit("Required monitoring checks failed: " + "; ".join(c["name"] for c in failed))
    print("MONITORING_EVIDENCE_VERIFIED: Prometheus and Grafana evidence collected on the runner")
