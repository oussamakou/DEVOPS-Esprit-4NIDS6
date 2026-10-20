"""Install pinned scanner/validator binaries, verifying release SHA256 manifests.

Usage: python scripts/install-tools.py terraform gitleaks trivy actionlint
Windows and Linux x86_64 only. Binaries stay in the ignored .tools directory.
"""
import hashlib
import io
import os
from pathlib import Path
import platform
import sys
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = {"terraform": "1.13.5", "gitleaks": "8.30.1", "trivy": "0.76.0", "actionlint": "1.7.11", "k3d": "5.9.0"}


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "student-devsecops-lab"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def install(name):
    version = VERSIONS[name]
    windows = platform.system() == "Windows"
    system = "windows" if windows else "linux"
    ext = "zip" if name == "terraform" or windows else "tar.gz"
    if platform.machine().lower() not in ("amd64", "x86_64"):
        raise RuntimeError("This helper supports x86_64 only.")
    if name == "k3d":
        base = f"https://github.com/k3d-io/k3d/releases/download/v{version}"
        archive = f"k3d-{system}-amd64" + (".exe" if windows else "")
        manifest = "checksums.txt"
    elif name == "terraform":
        base = f"https://releases.hashicorp.com/terraform/{version}"
        archive = f"terraform_{version}_{system}_amd64.zip"
        manifest = f"terraform_{version}_SHA256SUMS"
    else:
        repos = {"gitleaks": "gitleaks/gitleaks", "trivy": "aquasecurity/trivy", "actionlint": "rhysd/actionlint"}
        base = f"https://github.com/{repos[name]}/releases/download/v{version}"
        if name == "trivy":
            archive = f"trivy_{version}_{'windows' if windows else 'Linux'}-64bit.{ext}"
        elif name == "gitleaks":
            archive = f"gitleaks_{version}_{system}_x64.{ext}"
        else:
            archive = f"actionlint_{version}_{system}_amd64.{ext}"
        manifest = f"{name}_{version}_checksums.txt"
    destination = ROOT / ".tools" / (name + (".exe" if windows else ""))
    destination.parent.mkdir(exist_ok=True)
    # Recheck downloads on every invocation. Do not silently trust a stale local tool.
    sums = fetch(f"{base}/{manifest}").decode()
    matching = [line.split()[0] for line in sums.splitlines() if line.split()[-1].lstrip("*") == archive]
    if len(matching) != 1:
        raise RuntimeError(f"No unique checksum for {archive}")
    payload = fetch(f"{base}/{archive}")
    if hashlib.sha256(payload).hexdigest() != matching[0]:
        raise RuntimeError(f"Checksum mismatch: {archive}")
    binary = name + (".exe" if windows else "")
    if name == "k3d":
        data = payload
    elif ext == "zip":
        with zipfile.ZipFile(io.BytesIO(payload)) as compressed:
            data = compressed.read(binary)
    else:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as compressed:
            candidates = [m for m in compressed.getmembers() if m.isfile() and Path(m.name).name == binary]
            if len(candidates) != 1:
                raise RuntimeError("Unexpected archive contents")
            data = compressed.extractfile(candidates[0]).read()
    destination.write_bytes(data)
    destination.chmod(0o755)
    print(f"Installed {name} {version} ({system})")


if __name__ == "__main__":
    for tool in sys.argv[1:]:
        if tool not in VERSIONS:
            raise SystemExit(f"Unknown tool: {tool}")
        install(tool)
