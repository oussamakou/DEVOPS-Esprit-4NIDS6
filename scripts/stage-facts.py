"""Record verified facts about what a pipeline stage produced (digest, URL, size...).

Usage: python scripts/stage-facts.py REPORT_DIR NAME key=value [key=value ...]

Writes REPORT_DIR/NAME-facts.json. The report renderer shows these next to the
stage's captured command log. Values are recorded verbatim; never pass secrets.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys


def record(folder, name, pairs):
    facts = {}
    for pair in pairs:
        key, separator, value = pair.partition("=")
        if not separator or not key.replace("_", "").replace("-", "").isalnum():
            raise ValueError(f"Expected key=value with a simple key, got {pair!r}")
        facts[key] = value
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    document = {"stage": name, "recorded_utc": datetime.now(timezone.utc).isoformat(),
                "commit": os.environ.get("GITHUB_SHA", "local"), "facts": facts}
    (folder / f"{name}-facts.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as stream:
            stream.write(f"- **{name}** facts: " + ", ".join(f"{k}=`{v}`" for k, v in facts.items()) + "\n")
    return document


if __name__ == "__main__":
    if len(sys.argv) < 4 or not sys.argv[2].replace("-", "").isalnum():
        raise SystemExit(__doc__)
    record(sys.argv[1], sys.argv[2], sys.argv[3:])
    print(f"FACTS_RECORDED: {sys.argv[2]}")
