"""Controlled XML fixtures verify acceptance fails closed; no network scans run here."""
import importlib.util
import base64
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


nmap = module("acceptance", "nmap-acceptance.py")
azure = module("azure_acceptance", "azure-nmap-acceptance.py")
probe = module("vm_probe", "nmap-vm-probe.py")
POLICY = nmap.load_policy(ROOT / "security/nmap-policy.json")


def fixture(path, profile, opened=None, aggregate="closed"):
    opened = profile["required_open"] if opened is None else opened
    root = ET.Element("nmaprun", scanner="nmap")
    ET.SubElement(root, "scaninfo", type="connect", protocol="tcp", services=POLICY["ports"], numservices=str(len(nmap.expand_ports(POLICY["ports"]))))
    host = ET.SubElement(root, "host")
    ET.SubElement(host, "status", state="up")
    ET.SubElement(host, "address", addr=profile["target"], addrtype="ipv4")
    ports = ET.SubElement(host, "ports")
    for number in opened:
        ET.SubElement(ET.SubElement(ports, "port", protocol="tcp", portid=str(number)), "state", state="open", reason="conn-accepted")
    ET.SubElement(ports, "extraports", state=aggregate, count=str(len(nmap.expand_ports(POLICY["ports"])) - len(opened)))
    ET.SubElement(ET.SubElement(root, "runstats"), "finished", exit="success")
    ET.ElementTree(root).write(path, encoding="utf-8")
    return root


class AcceptanceTests(unittest.TestCase):
    def assess(self, profile, opened=None, mutate=None, aggregate="closed"):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "controlled-fixture.xml"
            root = fixture(path, profile, opened, aggregate)
            if mutate:
                mutate(root)
                ET.ElementTree(root).write(path, encoding="utf-8")
            return nmap.assess_xml(path, profile, POLICY["ports"])

    def test_expected_https_passes(self):
        self.assertEqual(self.assess(POLICY["profiles"]["public"][1])["status"], "passed")

    def test_exposed_database_fails(self):
        result = self.assess(POLICY["profiles"]["public"][1], [443, 8443, 3306])
        self.assertEqual(result["unexpected_open"], [3306])
        self.assertEqual(result["status"], "failed")

    def test_missing_https_fails(self):
        result = self.assess(POLICY["profiles"]["public"][1], [443])
        self.assertEqual(result["missing_required"], [8443])

    def test_all_filtered_cannot_satisfy_required_services(self):
        self.assertEqual(self.assess(POLICY["profiles"]["private"][1], [], aggregate="filtered")["status"], "failed")

    def test_public_app_is_expected_to_be_filtered_from_external_runner(self):
        self.assertEqual(self.assess(POLICY["profiles"]["public"][0], [], aggregate="filtered")["status"], "passed")

    def test_incomplete_scan_cannot_pass(self):
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            self.assess(POLICY["profiles"]["public"][1], mutate=lambda r: r.find("host/ports/extraports").set("count", "0"))

    def test_wrong_target_cannot_pass(self):
        with self.assertRaisesRegex(ValueError, "target"):
            self.assess(POLICY["profiles"]["public"][1], mutate=lambda r: r.find("host/address").set("addr", "192.0.2.1"))

    def test_failed_nmap_run_cannot_pass(self):
        with self.assertRaisesRegex(ValueError, "completed"):
            self.assess(POLICY["profiles"]["public"][1], mutate=lambda r: r.find("runstats/finished").set("exit", "error"))

    def test_host_timeout_cannot_pass_even_with_success_exit_and_ports(self):
        with self.assertRaisesRegex(ValueError, "host timeout"):
            self.assess(POLICY["profiles"]["public"][1], mutate=lambda r: r.find("host").set("timedout", "true"))

    def test_ambiguous_port_state_cannot_pass(self):
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            self.assess(POLICY["profiles"]["public"][1], mutate=lambda r: r.find("host/ports/port/state").set("state", "open|filtered"))

    def test_duplicate_or_shortened_coverage_cannot_pass(self):
        with self.assertRaisesRegex(ValueError, "coverage"):
            self.assess(POLICY["profiles"]["public"][1], mutate=lambda r: r.find("scaninfo").set("services", "443,8443"))

    def test_missing_scanner_records_error(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(nmap.shutil, "which", return_value=None):
            result = nmap.run_view("public", directory)
            self.assertEqual(result["status"], "error")
            self.assertTrue((Path(directory) / "result.json").is_file())

    def test_no_raw_xml_cannot_be_replaced_by_green_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for view in ("public", "private"):
                folder = root / view
                folder.mkdir()
                (folder / "result.json").write_text(json.dumps({"view": view, "policy_sha256": nmap.policy_hash(POLICY), "status": "passed", "profiles": [{"name": p["name"], "status": "passed", "target": p["target"]} for p in POLICY["profiles"][view]]}))
            self.assertFalse(nmap.combine(root))
            self.assertTrue((root / "index.html").is_file())

    def test_archive_path_traversal_is_rejected(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("../escape.txt", "controlled fixture")
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "path"):
            azure.unpack_reports(archive.getvalue(), Path(directory))

    def test_complete_original_reports_can_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for view in ("public", "private"):
                folder = root / view
                folder.mkdir()
                items = []
                for profile in POLICY["profiles"][view]:
                    fixture(folder / f"{profile['name']}.xml", profile)
                    (folder / f"{profile['name']}.nmap").write_text("Controlled unit-test fixture, not live scan evidence.")
                    items.append(nmap.assess_xml(folder / f"{profile['name']}.xml", profile, POLICY["ports"]))
                (folder / "nmap-version.txt").write_text("Controlled fixture")
                (folder / "result.json").write_text(json.dumps({"view": view, "policy_sha256": nmap.policy_hash(POLICY), "status": "passed", "profiles": items}))
            self.assertTrue(nmap.combine(root))

    def test_coursework_acceptance_follows_deploy_and_blocks_monitoring(self):
        import yaml
        jobs = yaml.safe_load((ROOT / ".github/workflows/coursework.yml").read_text())["jobs"]
        self.assertEqual(jobs["delivery"]["needs"], "security")
        self.assertEqual(jobs["acceptance"]["needs"], "delivery")
        self.assertEqual(jobs["acceptance"]["uses"], "./.github/workflows/acceptance-nmap.yml")
        self.assertIn("acceptance", jobs["monitoring"]["needs"])
        self.assertIn("acceptance", jobs["email"]["needs"])

    def test_transport_chunks_fit_azure_output_and_reassemble_original_bytes(self):
        payload = bytes(range(256)) * 80
        identifier = "a" * 32
        with tempfile.TemporaryDirectory() as directory, patch.object(probe, "STORE", Path(directory)):
            folder = Path(directory) / identifier
            folder.mkdir()
            (folder / "reports.zip").write_bytes(payload)
            chunks = []
            for index in range((len(base64.b64encode(payload)) + probe.CHUNK - 1) // probe.CHUNK):
                text = io.StringIO()
                with redirect_stdout(text):
                    probe.emit(identifier, index)
                self.assertLess(len(text.getvalue().encode()), 4096)
                chunks.append(json.loads(text.getvalue().split(" ", 1)[1])["payload"])
            self.assertEqual(base64.b64decode(''.join(chunks)), payload)


if __name__ == "__main__":
    unittest.main()
