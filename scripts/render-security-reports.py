"""Create a readable index of original scanner artifacts, including failures."""
import html
import json
import os
from pathlib import Path
import re
import sys


def render(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    esc = html.escape
    rows = []
    for path in sorted(folder.rglob("*-result.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        rows.append((result["check"], result["status"], str(result["exit_code"]), result["finished_utc"], path.relative_to(folder).as_posix()))
    jobs = json.loads(os.environ.get("SECURITY_JOB_RESULTS", "{}"))
    package_count = "not available"
    inventory = folder / "dependencies/inventory-summary.json"
    if inventory.exists():
        details = json.loads(inventory.read_text())
        package_count = str(details["packages_analyzed"])
    stats = []
    for path in sorted(folder.glob("iac/checkov-*.json")):
        if path.name.endswith("-result.json"):
            continue
        data = json.loads(path.read_text())
        for report in data if isinstance(data, list) else [data]:
            if "summary" in report:
                summary = report["summary"]
                stats.append(f"{path.name}: {summary.get('passed', 0)} passed, {summary.get('failed', 0)} failed, {summary.get('skipped', 0)} skipped")
    semgrep = folder / "sast/semgrep.json"
    if semgrep.exists():
        data = json.loads(semgrep.read_text())
        stats.append(f"Semgrep: {len(data.get('paths', {}).get('scanned', []))} files scanned, {len(data.get('results', []))} application findings, {len(data.get('errors', []))} scanner errors")
    stats.append(f"Source dependency packages analyzed: {package_count}")
    run = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
    head = os.environ.get("GITHUB_SHA", "local")
    files = [p for p in sorted(folder.rglob("*")) if p.is_file() and p.name != "index.html"]
    body = """<!doctype html><html lang="en"><meta charset="utf-8"><title>Pre-build security evidence</title>
<style>body{font:17px/1.5 Arial,sans-serif;color:#172332;max-width:1100px;margin:40px auto;padding:0 24px}h1{font-size:32px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:10px;text-align:left}th{background:#eef3f7}a{color:#075e91}code{overflow-wrap:anywhere}li{margin:8px 0}@media print{body{margin:0;font-size:12px}a{color:inherit}}</style>"""
    body += f"<h1>Pre-build security evidence</h1><p>Revision: <code>{esc(head)}</code><br>Run: <a href='{esc(run)}'>{esc(run)}</a></p>"
    body += "<p>Order: checkout, local-hook replay, commit security gates, then Maven compilation. Threat modeling remains a human review activity. A saved document does not prove a human review occurred.</p>"
    if jobs:
        body += "<h2>Security job outcomes</h2><ul>" + "".join(f"<li>{esc(name)}: {esc(value['result'])}</li>" for name, value in jobs.items()) + "</ul>"
    body += "<h2>Scanner measurements</h2><ul>" + "".join(f"<li>{esc(s)}</li>" for s in stats) + "</ul>"
    body += "<h2>Actual command outcomes</h2><table><tr><th>Check</th><th>Result</th><th>Exit</th><th>Finished UTC</th><th>Original record</th></tr>"
    for check, status, code, finished, record in rows:
        body += f"<tr><td>{esc(check)}</td><td>{esc(status)}</td><td>{esc(code)}</td><td>{esc(finished)}</td><td><a href='{esc(record)}'>JSON record</a></td></tr>"
    body += "</table><p>Missing results mean a command did not finish or did not run. CI history scanning complements local staged-secret hooks. Controlled exercises use temporary fixtures and are separate from application findings. The source POM scan excludes test and optional dependencies. Checkov skipped policies remain listed in the raw reports and documented configuration.</p>"
    body += "<h2>Downloadable original reports and logs</h2><ul>" + "".join(f"<li><a href='{esc(p.relative_to(folder).as_posix())}'>{esc(p.relative_to(folder).as_posix())}</a></li>" for p in files) + "</ul></html>"
    (folder / "index.html").write_text(body, encoding="utf-8")
    for name in ("precommit", "sast", "secrets", "iac", "dependencies"):
        section = folder / name
        if not section.is_dir():
            continue
        page = body[:body.index("<h1>")]
        page += f"<h1>{esc(name)}: original security evidence</h1><p>Revision: <code>{esc(head)}</code><br><a href='{esc(run)}'>Actions run</a> / <a href='../index.html'>All checks</a></p>"
        page += "<p>This page renders the original tool transcripts. It is an assessment report, not a separate vendor dashboard.</p>"
        if name == "dependencies" and inventory.exists():
            page += "<h2>Verified inventory</h2><pre>" + esc(json.dumps(details, indent=2)) + "</pre>"
        if name == "iac":
            page += "<h2>Policy counts</h2><ul>" + "".join(f"<li>{esc(s)}</li>" for s in stats if s.startswith("checkov")) + "</ul>"
        for outcome in sorted(section.glob("*-result.json")):
            record = json.loads(outcome.read_text())
            page += f"<h2>{esc(record['check'])}: {esc(record['status'])}</h2><p>Exit {record['exit_code']}. Finished {esc(record['finished_utc'])}</p>"
        for log in sorted(section.glob("*.log")):
            transcript = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", log.read_text(encoding="utf-8"))
            page += f"<h2>{esc(log.name)}</h2><pre style='white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:18px'>{esc(transcript)}</pre>"
        if name == "precommit":
            page += "<p>The STRIDE threat model is preserved as THREAT-MODEL.md. It remains a human review activity.</p>"
        page += "</html>"
        (section / "report.html").write_text(page, encoding="utf-8")
    summary = "## Security checks before Maven\n\n" + "\n".join(f"- {name}: **{value['result']}**" for name, value in jobs.items())
    summary += "\n\n" + "\n".join(f"- {s}" for s in stats)
    summary += "\n\nDownload **professor-security-reports** and open **index.html** for raw reports, logs and the threat model.\n"
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as stream:
            stream.write(summary)
    (folder / "README.md").write_text(summary, encoding="utf-8")
    print(f"Readable report written to {folder / 'index.html'}")


if __name__ == "__main__":
    render(sys.argv[1])
