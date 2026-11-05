"""Report aggregation preserves phase results and does not invent missing scans."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("reports", ROOT / "scripts/render-security-reports.py")
reports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reports)


class ReportTests(unittest.TestCase):
    def add_nmap(self, root, status="passed"):
        folder = root / "acceptance"
        folder.mkdir()
        data = {"status": status, "results": [{"view": "public", "profiles": [
            {"name": "app-public", "target": "192.0.2.1", "status": status, "ports_scanned": 1040,
             "open_ports": [] if status == "passed" else [3306], "unexpected_open": [] if status == "passed" else [3306]}]}]}
        (folder / "acceptance-result.json").write_text(json.dumps(data))
        (folder / "index.html").write_text("<html>Controlled Nmap report fixture</html>")

    def test_nmap_and_command_records_share_one_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.add_nmap(root)
            (root / "hooks-result.json").write_text(json.dumps({"check": "hooks", "status": "passed", "exit_code": 0, "finished_utc": "2026-11-05T00:00:00Z"}))
            reports.render(root)
            text = (root / "index.html").read_text(encoding="utf-8")
            self.assertIn("Acceptance phase: Nmap", text)
            self.assertIn("1040", text)
            self.assertIn("hooks", text)
            self.assertEqual((root / "acceptance/report.html").read_text(), (root / "acceptance/index.html").read_text())

    def test_failed_nmap_is_not_hidden_by_passed_prebuild_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.add_nmap(root, "failed")
            reports.render(root)
            text = (root / "index.html").read_text(encoding="utf-8")
            self.assertIn("<strong>failed</strong>", text)
            self.assertIn("3306", text)

    def test_prebuild_snapshot_does_not_claim_nmap_ran(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports.render(root)
            text = (root / "index.html").read_text(encoding="utf-8")
            self.assertIn("Nmap acceptance is not available in this snapshot", text)
            self.assertNotIn("Nmap acceptance: passed", text)

    def test_acceptance_only_snapshot_does_not_claim_dependency_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.add_nmap(root)
            reports.render(root)
            self.assertIn("Source dependency packages analyzed: not available", (root / "index.html").read_text())


if __name__ == "__main__":
    unittest.main()
