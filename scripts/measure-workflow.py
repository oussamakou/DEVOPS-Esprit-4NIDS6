"""Export GitHub run timing using the authenticated GitHub CLI; no credentials printed."""
import json
import subprocess
import sys
from datetime import datetime

repo, run = sys.argv[1:3]
if not run.isdecimal() or repo.count("/") != 1:
    raise SystemExit("Usage: measure-workflow.py OWNER/REPO NUMERIC_RUN_ID")
data = json.loads(subprocess.check_output(["gh", "api", f"repos/{repo}/actions/runs/{run}"], text=True))
jobs = json.loads(subprocess.check_output(["gh", "api", f"repos/{repo}/actions/runs/{run}/jobs?per_page=100"], text=True))
def duration(start, end):
    return (datetime.fromisoformat(end.replace("Z", "+00:00")) - datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds()
result = {"url": data["html_url"], "commit": data["head_sha"], "conclusion": data["conclusion"],
          "wall_seconds": duration(data["created_at"], data["updated_at"]), "jobs": []}
for job in jobs["jobs"]:
    result["jobs"].append({"name": job["name"], "conclusion": job["conclusion"],
                           "seconds": duration(job["started_at"], job["completed_at"]) if job["completed_at"] else None})
print(json.dumps(result, indent=2))
