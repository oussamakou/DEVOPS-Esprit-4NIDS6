"""Screenshot the live tool UIs inside the disposable runner with headless Chrome.

Usage: python scripts/capture-ui-screenshots.py OUTPUT_DIR GROUP name=URL [name=URL ...]

Only 127.0.0.1 URLs are accepted: these are the runner's own SonarQube, Nexus,
Grafana, Prometheus and API, never an external site. Each image is checked to
exist and to be larger than an empty page. Writes screenshots-GROUP-facts.json; exits
non-zero if any screenshot is missing (the workflow treats that as evidence, not a gate).
"""
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import urlparse

MIN_BYTES = 15_000  # a blank 1440x1000 PNG is far smaller than any rendered tool page


def chrome():
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        if shutil.which(name):
            return shutil.which(name)
    raise SystemExit("No Chrome or Chromium binary found on this runner")


def capture(output, group, pairs):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    # Validate every request before anything runs: never open a URL outside this runner.
    requests = []
    for pair in pairs:
        name, _, url = pair.partition("=")
        if not re.fullmatch(r"[a-z0-9-]+", name) or urlparse(url).hostname != "127.0.0.1":
            raise SystemExit(f"Refusing {pair!r}: names are lowercase-hyphenated and URLs must be 127.0.0.1")
        requests.append((name, url))
    binary, taken, missing = chrome(), {}, []
    for name, url in requests:
        target = output / f"{name}.png"
        # --no-sandbox: Ubuntu 24.04 restricts the user namespaces Chrome's sandbox needs; this runner is disposable.
        subprocess.run([binary, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                        "--window-size=1440,1000", "--virtual-time-budget=25000", f"--screenshot={target}", url],
                       capture_output=True, text=True, timeout=120)
        if target.is_file() and target.stat().st_size >= MIN_BYTES:
            taken[name] = {"url": url, "bytes": target.stat().st_size}
            print(f"captured {name}: {url} ({target.stat().st_size} bytes)")
        else:
            missing.append(name)
            print(f"MISSING {name}: {url}")
    facts = {**{f"{n}_url": v["url"] for n, v in taken.items()},
             f"{group}_captured": str(len(taken)), f"{group}_missing": ", ".join(missing) or "none"}
    (output / f"screenshots-{group}-facts.json").write_text(
        json.dumps({"stage": f"screenshots-{group}", "facts": facts}, indent=2) + "\n", encoding="utf-8")
    return not missing


if __name__ == "__main__":
    if len(sys.argv) < 4 or not re.fullmatch(r"[a-z0-9-]+", sys.argv[2]):
        raise SystemExit(__doc__)
    sys.exit(0 if capture(sys.argv[1], sys.argv[2], sys.argv[3:]) else 1)
