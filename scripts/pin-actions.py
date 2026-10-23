"""Resolve official action tags to immutable commits. Review the diff before committing."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import urllib.request

path = Path(__file__).resolve().parents[1] / ".github/workflows/devsecops.yml"
source = path.read_text(encoding="utf-8")
references = sorted(set(re.findall(r"uses: ([\w-]+/[\w-]+)@(v[\w.]+)", source)))

def resolve(reference):
    repo, tag = reference
    url = f"https://api.github.com/repos/{repo}/git/ref/tags/{tag}"
    req = urllib.request.Request(url, headers={"User-Agent": "student-devsecops-lab"})
    with urllib.request.urlopen(req, timeout=30) as response:
        obj = json.load(response)["object"]
    if obj["type"] == "tag":
        req = urllib.request.Request(obj["url"], headers={"User-Agent": "student-devsecops-lab"})
        with urllib.request.urlopen(req, timeout=30) as response:
            obj = json.load(response)["object"]
    if obj["type"] != "commit" or not re.fullmatch(r"[a-f0-9]{40}", obj["sha"]):
        raise RuntimeError(f"Unexpected ref for {repo}@{tag}")
    return repo, tag, obj["sha"]

with ThreadPoolExecutor(max_workers=4) as pool:
    resolved = list(pool.map(resolve, references))
for repo, tag, sha in resolved:
    source = source.replace(f"uses: {repo}@{tag}", f"uses: {repo}@{sha} # {tag}")
    print(f"{repo}@{tag} -> {sha}")
path.write_text(source, encoding="utf-8")
