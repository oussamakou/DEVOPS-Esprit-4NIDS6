"""Regression tests for build gating, nonempty inventory and recorded failures."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("dependency_scan", ROOT / "scripts/scan-maven-dependencies.py")
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)


class SecurityEvidenceTests(unittest.TestCase):
    def test_both_maven_entrypoints_wait_for_security(self):
        for name, job in [("devsecops", "build"), ("coursework", "delivery")]:
            workflow = yaml.safe_load((ROOT / f".github/workflows/{name}.yml").read_text())
            self.assertEqual(workflow["jobs"][job]["needs"], "security")
            self.assertEqual(workflow["jobs"]["security"]["uses"], "./.github/workflows/prebuild-security.yml")
        security = yaml.safe_load((ROOT / ".github/workflows/prebuild-security.yml").read_text())
        for gate in ("sast", "secrets", "dependencies", "iac"):
            self.assertEqual(security["jobs"][gate]["needs"], "precommit")
        self.assertNotIn("mvnw", (ROOT / ".github/workflows/prebuild-security.yml").read_text())

    def test_empty_or_partial_inventory_is_rejected(self):
        for report in ({}, {"Results": []}, {"Results": [{"Type": "pom", "Packages": [{"Name": "unrelated", "Version": "1"}]}]}):
            with self.assertRaises(ValueError):
                scan.inventory(report)

    def test_unresolved_versions_are_rejected(self):
        names = ["org.springframework:spring-webmvc", "org.apache.tomcat.embed:tomcat-embed-core",
                 "com.mysql:mysql-connector-j", "org.springdoc:springdoc-openapi-starter-webmvc-ui"]
        packages = [{"Name": n, "Version": "1", "Identifier": {"PURL": "pkg:maven/" + n.replace(":", "/") + "@1"}} for n in names]
        self.assertEqual(len(scan.inventory({"Results": [{"Type": "pom", "Packages": packages}]})), 4)
        packages[0]["Version"] = ""
        with self.assertRaises(ValueError):
            scan.inventory({"Results": [{"Type": "pom", "Packages": packages}]})

    def test_check_failure_stays_failed_in_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([sys.executable, str(ROOT / "scripts/capture-check.py"), "fixture", folder,
                                     "--", sys.executable, "-c", "print('controlled failure'); raise SystemExit(7)"], capture_output=True)
            self.assertEqual(result.returncode, 7)
            record = json.loads((Path(folder) / "fixture-result.json").read_text())
            self.assertEqual(record["status"], "failed")
            self.assertEqual(record["exit_code"], 7)
            self.assertIn("controlled failure", (Path(folder) / "fixture.log").read_text())


if __name__ == "__main__":
    unittest.main()
