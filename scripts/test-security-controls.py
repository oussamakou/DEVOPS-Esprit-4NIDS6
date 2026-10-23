"""Regression checks for the blocking local hook, including legacy encoding."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CHECKER = Path(__file__).with_name("check-files.py")


class FileGateTests(unittest.TestCase):
    def run_fixture(self, name, content, encoding="utf-8"):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / name
            path.write_text(content, encoding=encoding)
            return subprocess.run([sys.executable, str(CHECKER), str(path)], capture_output=True, text=True)

    def test_valid_yaml(self):
        self.assertEqual(self.run_fixture("good.yml", "service: app\n").returncode, 0)

    def test_malformed_yaml_is_blocked(self):
        self.assertEqual(self.run_fixture("bad.yml", "service: [unclosed\n").returncode, 1)

    def test_malformed_xml_is_blocked(self):
        self.assertEqual(self.run_fixture("pom.xml", "<project>\n").returncode, 1)

    def test_utf16_text_is_checked(self):
        self.assertEqual(self.run_fixture("guide.md", "Legacy guide\n", "utf-16").returncode, 0)
        self.assertEqual(self.run_fixture("guide.md", "<<<<<<< unresolved\n", "utf-16").returncode, 1)

    def test_private_key_is_blocked_without_echoing_contents(self):
        marker = "-----BEGIN " + "OPENSSH PRIVATE KEY-----"
        result = self.run_fixture("secret.txt", marker + "\nsensitive-fixture\n")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("sensitive-fixture", result.stdout)


if __name__ == "__main__":
    unittest.main()
