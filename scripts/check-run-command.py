"""Azure CLI can return success even when a guest shell script failed."""
import json
import sys

with open(sys.argv[1], encoding="utf-8") as file:
    result = json.load(file)
messages = "\n".join(item.get("message", "") for item in result.get("value", []))
print(messages)
if not any(line.startswith("DEPLOY_SUCCEEDED ") for line in messages.splitlines()):
    raise SystemExit("Guest deployment did not report a successful rollout and smoke test")
