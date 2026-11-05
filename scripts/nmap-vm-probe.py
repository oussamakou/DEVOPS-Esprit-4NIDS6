"""Azure guest helper: keep original reports and return bounded, checksummed chunks."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import uuid
import zipfile

STORE = Path("/opt/student-course/acceptance/nmap")
CHUNK = 2000  # Azure Run Command only retains a small stdout tail.


def emit(identifier, index):
    if not re.fullmatch(r"[a-f0-9]{32}", identifier):
        raise ValueError("Invalid report identifier")
    payload = (STORE / identifier / "reports.zip").read_bytes()
    encoded = base64.b64encode(payload).decode("ascii")
    count = (len(encoded) + CHUNK - 1) // CHUNK
    if not 0 <= index < count:
        raise ValueError("Invalid report chunk")
    message = {"id": identifier, "index": index, "chunks": count,
               "sha256": hashlib.sha256(payload).hexdigest(), "payload": encoded[index * CHUNK:(index + 1) * CHUNK]}
    print("NMAP_REPORT_V1 " + json.dumps(message, separators=(",", ":")))


def main():
    mode = sys.argv[1]
    if mode == "fetch":
        emit(sys.argv[2], int(sys.argv[3]))
        return
    if mode != "scan":
        raise ValueError("Expected scan or fetch")
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("acceptance", root / "scripts/nmap-acceptance.py")
    acceptance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acceptance)
    identifier = uuid.uuid4().hex
    destination = STORE / identifier
    destination.mkdir(mode=0o700, parents=True)
    acceptance.run_view("private", destination)
    with zipfile.ZipFile(destination / "reports.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(destination.iterdir()):
            if path.is_file() and path.name != "reports.zip":
                archive.write(path, path.name)
    # Persist only this retrieval helper. It contains no credentials.
    (STORE / "fetch-reports.py").write_bytes(Path(__file__).read_bytes())
    emit(identifier, 0)


if __name__ == "__main__":
    main()
