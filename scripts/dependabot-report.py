"""Production-phase report: Dependabot configuration, open update PRs and security alerts.

Reads the GitHub REST API with the workflow's GITHUB_TOKEN. The job needs
`pull-requests: read`, `checks: read` and `vulnerability-alerts: read` (the only
GITHUB_TOKEN permission that can read Dependabot alerts). Writes
REPORT_DIR/dependabot-evidence.json for render-security-reports.py.

Findings are reported, not blocking: the command exits 0 when the data was
collected, and non-zero only when the pull-request listing itself fails.
Disabled or unreadable alerts are recorded as a finding, never as "no alerts".

Usage: GITHUB_TOKEN=... GITHUB_REPOSITORY=owner/repo python scripts/dependabot-report.py REPORT_DIR
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[1]
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
FAILED_CONCLUSIONS = {"failure", "cancelled", "timed_out", "action_required", "startup_failure"}


def api(base, path, token):
    """Return (HTTP status, parsed JSON) without raising on 4xx, so callers can report access problems."""
    request = urllib.request.Request(base.rstrip("/") + path, headers={
        "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {token}", "User-Agent": "student-devsecops-report"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        try:
            body = json.load(error)
        except (json.JSONDecodeError, ValueError):
            body = {}
        return error.code, body


def parse_config(path):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return [{"ecosystem": u.get("package-ecosystem"), "directory": u.get("directory"),
             "interval": (u.get("schedule") or {}).get("interval"),
             "open_pull_requests_limit": u.get("open-pull-requests-limit", 5)} for u in data.get("updates", [])]


def split_version(version):
    """Split '3.9.11-eclipse-temurin-17' into ([3, 9, 11], '-eclipse-temurin-17')."""
    match = re.match(r"v?(\d+(?:\.\d+)*)(.*)$", version)
    return ([int(part) for part in match[1].split(".")], match[2]) if match else (None, version)


def parse_update(title, branch):
    match = re.search(r"[Bb]ump (?P<package>\S+) from (?P<old>\S+) to (?P<new>\S+)", title)
    ecosystem = branch.split("/")[1].replace("_", "-") if branch.startswith("dependabot/") and branch.count("/") >= 2 else "unknown"
    if not match:
        return {"ecosystem": ecosystem, "package": title, "from": "?", "to": "?", "update_type": "unknown"}
    (old, old_suffix), (new, new_suffix) = split_version(match["old"]), split_version(match["new"])
    if not old or not new:
        kind = "unknown"
    elif old_suffix != new_suffix:
        kind = "variant"  # e.g. a Docker tag moving from a JDK 17 to a JDK 26 base: not a simple version bump
    elif old[0] != new[0]:
        kind = "major"
    elif old[1:2] != new[1:2]:
        kind = "minor"
    else:
        kind = "patch"
    return {"ecosystem": ecosystem, "package": match["package"], "from": match["old"], "to": match["new"], "update_type": kind}


def ci_state(check_runs):
    if not check_runs:
        return "no checks"
    if any(run.get("status") != "completed" for run in check_runs):
        return "pending"
    if any(run.get("conclusion") in FAILED_CONCLUSIONS for run in check_runs):
        return "failing"
    return "passing"


def collect(repo, token, base="https://api.github.com", config=ROOT / ".github/dependabot.yml", now=None):
    now = now or datetime.now(timezone.utc)
    evidence = {"generated_utc": now.isoformat(), "repository": repo, "config": parse_config(config), "checks": []}
    status, pulls = api(base, f"/repos/{repo}/pulls?state=open&per_page=100", token)
    if status != 200:
        raise RuntimeError(f"Could not list pull requests (HTTP {status}): {pulls.get('message', '')}")
    updates = []
    for pull in pulls:
        if pull.get("user", {}).get("login") != "dependabot[bot]":
            continue
        item = parse_update(pull["title"], pull["head"]["ref"])
        check_status, checks = api(base, f"/repos/{repo}/commits/{pull['head']['sha']}/check-runs?per_page=100", token)
        created = datetime.fromisoformat(pull["created_at"].replace("Z", "+00:00"))
        item.update({"number": pull["number"], "title": pull["title"], "url": pull["html_url"],
                     "created": pull["created_at"][:10], "age_days": (now - created).days,
                     "ci": ci_state(checks.get("check_runs", [])) if check_status == 200 else f"unreadable (HTTP {check_status})"})
        updates.append(item)
    evidence["update_pull_requests"] = sorted(updates, key=lambda u: u["number"])
    status, alerts = api(base, f"/repos/{repo}/dependabot/alerts?state=open&per_page=100", token)
    if status == 200:
        items = [{"number": a["number"], "severity": a["security_vulnerability"]["severity"],
                  "package": a["dependency"]["package"]["name"], "ecosystem": a["dependency"]["package"]["ecosystem"],
                  "manifest": a["dependency"].get("manifest_path"), "relationship": a["dependency"].get("relationship"),
                  "ghsa": a["security_advisory"]["ghsa_id"], "cve": a["security_advisory"].get("cve_id"),
                  "summary": a["security_advisory"]["summary"], "vulnerable_range": a["security_vulnerability"]["vulnerable_version_range"],
                  "patched": (a["security_vulnerability"].get("first_patched_version") or {}).get("identifier"),
                  "created": a["created_at"][:10], "url": a["html_url"]} for a in alerts]
        evidence["alerts"] = {"status": "enabled", "open": sorted(items, key=lambda a: SEVERITY_ORDER.get(a["severity"], 9))}
    else:
        message = alerts.get("message", "") if isinstance(alerts, dict) else ""
        state = "disabled" if "disabled" in message.lower() else "unreadable"
        evidence["alerts"] = {"status": state, "http_status": status, "message": message, "open": []}
    serious = [a for a in evidence["alerts"]["open"] if a["severity"] in ("critical", "high")]
    add = lambda name, ok, detail, required=True: evidence["checks"].append({"name": name, "ok": bool(ok), "detail": detail, "required": required})  # noqa: E731
    add("Dependabot version updates configured", evidence["config"],
        ", ".join(f"{c['ecosystem']} ({c['interval']})" for c in evidence["config"]) or "no update entries")
    add("Dependabot security alerts enabled and readable", evidence["alerts"]["status"] == "enabled",
        evidence["alerts"]["status"] if evidence["alerts"]["status"] == "enabled" else f"{evidence['alerts']['status']}: {evidence['alerts'].get('message', '')}")
    add("No open HIGH/CRITICAL Dependabot alerts", evidence["alerts"]["status"] == "enabled" and not serious,
        f"{len(serious)} open HIGH/CRITICAL" if evidence["alerts"]["status"] == "enabled" else "cannot be evaluated while alerts are not readable")
    failing = [u for u in updates if u["ci"] == "failing"]
    add("Open update PRs pass CI", not failing, f"{len(failing)} failing: " + ", ".join(f"#{u['number']}" for u in failing) if failing else "all passing or pending",
        required=False)
    evidence["summary"] = summary_lines(evidence)  # the renderer reads this; it has no YAML dependency
    return evidence


def summary_lines(evidence):
    updates = evidence["update_pull_requests"]
    risky = sum(1 for u in updates if u["update_type"] in ("major", "variant"))
    failing = sum(1 for u in updates if u["ci"] == "failing")
    oldest = max((u["age_days"] for u in updates), default=0)
    alerts = evidence["alerts"]
    alert_text = (f"{len(alerts['open'])} open security alerts" if alerts["status"] == "enabled"
                  else f"security alerts {alerts['status'].upper()}")
    return [f"{len(updates)} open update PRs ({risky} major or variant, {failing} failing CI, oldest {oldest} days)", alert_text,
            f"{len(evidence['config'])} ecosystems watched: " + ", ".join(c["ecosystem"] for c in evidence["config"])]


if __name__ == "__main__":
    if len(sys.argv) != 2 or not os.environ.get("GITHUB_TOKEN") or not os.environ.get("GITHUB_REPOSITORY"):
        raise SystemExit(__doc__)
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    result = collect(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"], os.environ.get("GITHUB_API_URL", "https://api.github.com"))
    (output / "dependabot-evidence.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for line in summary_lines(result):
        print("DEPENDABOT:", line)
    for check in result["checks"]:
        print(f"{'PASS' if check['ok'] else 'FINDING'}{'' if check['required'] else ' (informational)'}: {check['name']} - {check['detail']}")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as stream:
            stream.write("### Dependabot\n\n" + "\n".join(f"- {line}" for line in summary_lines(result)) + "\n")
