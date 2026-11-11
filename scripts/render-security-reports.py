"""Create a readable index of original pipeline artifacts, including failures.

Every stage writes its evidence into REPORT_DIR/<stage>/ (captured command logs
and *-result.json from capture-check.py, *-facts.json from stage-facts.py, and
the tool's own files). This script turns whatever exists into index.html plus a
report.html per stage. A stage with no evidence is shown as not run, never as passed.
"""
import html
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

# (folder, title, tools). Order is the pipeline order the professor follows.
STAGES = [
    ("precommit", "Pre-commit hooks and threat model", "pre-commit, Gitleaks hook"),
    ("sast", "Commit SAST", "Semgrep"),
    ("secrets", "Commit secrets scan", "Gitleaks"),
    ("dependencies", "Source dependency scan and SBOM", "Trivy, CycloneDX"),
    ("iac", "Infrastructure policy", "Terraform, Checkov"),
    ("build", "Compile, test and coverage", "Maven, Surefire, JaCoCo"),
    ("quality", "Code quality gate", "SonarQube"),
    ("artifact", "Artifact repository", "Nexus"),
    ("image", "Image build and vulnerability gate", "Docker, k3d smoke test, Trivy"),
    ("registry", "Image registry, deploy by digest", "OCI registry: ACR (Azure lane) or registry:2 (runner lane)"),
    ("deploy", "Deployment", "Docker Compose: Azure VM via Run Command, or the GitHub runner"),
    ("acceptance", "Network acceptance", "Nmap"),
    ("monitoring", "Monitoring verification", "API request, image and scrape-target check"),
    ("prometheus", "Metrics collection", "Prometheus, Node Exporter"),
    ("grafana", "Dashboards", "Grafana"),
    ("dependabot", "Dependency updates and security alerts", "Dependabot"),
]
LATER_STAGES = {"build", "quality", "artifact", "image", "registry", "deploy", "acceptance", "monitoring", "prometheus", "grafana", "dependabot"}
# Stages whose evidence carries its own checks. Dependabot findings need attention but do not block delivery.
EVIDENCE_STAGES = {"prometheus": "failed", "grafana": "failed", "dependabot": "attention"}
CHART_COLORS = ["#075e91", "#b35900", "#116329", "#8250df"]


def read_evidence(folder, name):
    path = Path(folder) / name / f"{name}-evidence.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def evidence_status(evidence, unmet="failed"):
    required = [c for c in evidence.get("checks", []) if c.get("required", True)]
    if not required:
        return "facts only"
    return "passed" if all(c["ok"] for c in required) else unmet


def dependabot_page(folder, esc):
    evidence = read_evidence(folder, "dependabot")
    if not evidence:
        return ""
    out = "<h2>Findings</h2><table><tr><th>Check</th><th>Result</th><th>Detail</th></tr>"
    for check in evidence["checks"]:
        outcome = "ok" if check["ok"] else ("needs attention" if check.get("required", True) else "not observed (informational)")
        css = "" if check["ok"] else " class='attention'"
        out += f"<tr><td>{esc(check['name'])}</td><td{css}>{esc(outcome)}</td><td>{esc(check['detail'])}</td></tr>"
    out += "</table>"
    alerts = evidence["alerts"]
    out += "<h2>Security alerts (Dependabot alerts API)</h2>"
    if alerts["status"] != "enabled":
        out += (f"<p class='banner'>Dependabot security alerts are <strong>{esc(alerts['status'])}</strong> for this repository "
                f"(HTTP {esc(str(alerts.get('http_status', '')))}: {esc(alerts.get('message', '').rstrip('.'))}). Vulnerable dependencies are therefore "
                "not being reported by Dependabot. The repository owner can enable them under Settings &gt; Code security "
                "(Dependabot alerts, and optionally Dependabot security updates). Trivy still scans dependencies before every build.</p>")
    elif not alerts["open"]:
        out += "<p>Alerts are enabled and there are no open Dependabot alerts.</p>"
    else:
        out += "<table><tr><th>Severity</th><th>Package</th><th>Advisory</th><th>Vulnerable range</th><th>Patched in</th><th>Manifest</th></tr>"
        for a in alerts["open"]:
            css = " class='failed'" if a["severity"] in ("critical", "high") else ""
            out += (f"<tr><td{css}>{esc(a['severity'])}</td><td>{esc(a['package'])} ({esc(a['ecosystem'])})</td>"
                    f"<td><a href='{esc(a['url'])}'>{esc(a['ghsa'])}</a> {esc(a.get('cve') or '')}<br>{esc(a['summary'])}</td>"
                    f"<td>{esc(a['vulnerable_range'])}</td><td>{esc(a.get('patched') or 'no fix yet')}</td><td>{esc(a.get('manifest') or '-')}</td></tr>")
        out += "</table>"
    out += "<h2>Open version-update pull requests</h2><p>Major and variant changes (for example a new JDK in a Docker tag) need a human review; failing CI blocks a merge.</p>"
    out += "<table><tr><th>PR</th><th>Ecosystem</th><th>Package</th><th>From</th><th>To</th><th>Change</th><th>Age</th><th>CI</th></tr>"
    for u in evidence["update_pull_requests"]:
        risky = u["update_type"] in ("major", "variant")
        out += (f"<tr><td><a href='{esc(u['url'])}'>#{u['number']}</a></td><td>{esc(u['ecosystem'])}</td><td>{esc(u['package'])}</td>"
                f"<td>{esc(u['from'])}</td><td>{esc(u['to'])}</td><td{' class=attention' if risky else ''}>{esc(u['update_type'])}</td>"
                f"<td>{u['age_days']} days</td><td{' class=failed' if u['ci'] == 'failing' else ''}>{esc(u['ci'])}</td></tr>")
    out += "</table><h2>Configuration (.github/dependabot.yml)</h2><table><tr><th>Ecosystem</th><th>Directory</th><th>Schedule</th><th>Open PR limit</th></tr>"
    out += "".join(f"<tr><td>{esc(str(c['ecosystem']))}</td><td>{esc(str(c['directory']))}</td><td>{esc(str(c['interval']))}</td>"
                   f"<td>{esc(str(c['open_pull_requests_limit']))}</td></tr>" for c in evidence["config"]) + "</table>"
    out += f"<p>Collected {esc(evidence['generated_utc'])} UTC from the GitHub API for {esc(evidence['repository'])}.</p>"
    return out


def monitoring_measurements(folder):
    lines = {"prometheus": [], "grafana": []}
    prometheus, grafana = read_evidence(folder, "prometheus"), read_evidence(folder, "grafana")
    if prometheus:
        targets = prometheus["prometheus"]["targets"]
        lines["prometheus"].append(f"{sum(1 for t in targets if t['health'] == 'up')} of {len(targets)} scrape targets UP")
        traffic = prometheus["traffic"]
        lines["prometheus"].append(f"{traffic['succeeded']}/{traffic['requests']} read-only API requests generated before sampling")
    if grafana:
        info = grafana["grafana"]
        lines["grafana"].append(f"database {info['health'].get('database')}, version {info['health'].get('version')}, "
                                f"{len(info['dashboards'])} provisioned dashboards, {len(info['datasources'])} data source(s)")
    return lines


def svg_chart(title, series, esc):
    points = [(t, v) for s in series for t, v in s["values"] if v is not None]
    if not points:
        return f"<p><strong>{esc(title)}</strong>: Prometheus returned no data for this window.</p>"
    t0, t1 = min(t for t, _ in points), max(t for t, _ in points)
    low, high = min(v for _, v in points), max(v for _, v in points)
    span_t, span_v = (t1 - t0) or 1, (high - low) or 1
    width, height = 520, 140
    lines, legend = [], []
    for index, item in enumerate(series):
        color = CHART_COLORS[index % len(CHART_COLORS)]
        coords = " ".join(f"{8 + (t - t0) / span_t * (width - 16):.1f},{height - 10 - (v - low) / span_v * (height - 24):.1f}"
                          for t, v in item["values"] if v is not None)
        lines.append(f"<polyline fill='none' stroke='{color}' stroke-width='2' points='{coords}'/>")
        label = ", ".join(f"{k}={v}" for k, v in item["metric"].items() if k in ("host", "instance", "job")) or "series"
        legend.append(f"<span style='color:{color}'>&#9632;</span> {esc(label)}")
    return (f"<h3>{esc(title)}</h3><svg viewBox='0 0 {width} {height}' width='{width}' role='img' aria-label='{esc(title)}' "
            f"style='background:#f4f6f8;border:1px solid #bbb'>{''.join(lines)}</svg>"
            f"<p>min {low:.4g}, max {high:.4g} over {(t1 - t0) // 60} minutes. {' &nbsp; '.join(legend)}</p>")


def monitoring_page(name, folder, esc):
    evidence = read_evidence(folder, name)
    if not evidence:
        return ""
    html_out = "<h2>Checks</h2><table><tr><th>Check</th><th>Result</th><th>Detail</th></tr>"
    for check in evidence["checks"]:
        outcome = "passed" if check["ok"] else ("failed" if check.get("required", True) else "not observed (informational)")
        html_out += f"<tr><td>{esc(check['name'])}</td><td>{esc(outcome)}</td><td>{esc(check['detail'])}</td></tr>"
    html_out += "</table>"
    if name == "prometheus":
        info = evidence["prometheus"]
        html_out += f"<p>Sampled at {esc(evidence['generated_utc'])} UTC after {evidence['traffic']['succeeded']}/{evidence['traffic']['requests']} read-only requests to <code>{esc(evidence['traffic']['endpoint'])}</code>. Alerting rule groups configured: {info['rule_groups']} (no Alertmanager notifications exist).</p>"
        html_out += "<h2>Scrape targets (Prometheus /api/v1/targets)</h2><table><tr><th>Job</th><th>Instance</th><th>Host</th><th>Health</th><th>Last scrape</th><th>Last error</th></tr>"
        for t in info["targets"]:
            html_out += "<tr>" + "".join(f"<td>{esc(str(t.get(k) or '-'))}</td>" for k in ("job", "instance", "host", "health", "last_scrape", "last_error")) + "</tr>"
        html_out += "</table><h2>Instant query values</h2><table><tr><th>Metric</th><th>PromQL</th><th>Value</th></tr>"
        for title, item in info["instant"].items():
            values = "; ".join(f"{', '.join(f'{k}={v}' for k, v in r['metric'].items() if k in ('host', 'instance')) or 'total'}: {r['value']}" for r in item["result"]) or "no series"
            html_out += f"<tr><td>{esc(title)}</td><td><code>{esc(item['expression'])}</code></td><td>{esc(values)}</td></tr>"
        html_out += "</table><p>An empty series is not a measured zero: it means Prometheus has no matching samples.</p>"
    else:
        info = evidence["grafana"]
        html_out += f"<h2>Grafana health</h2><pre>{esc(json.dumps(info['health'], indent=2))}</pre>"
        html_out += "<h2>Provisioned data sources</h2><table><tr><th>Name</th><th>Type</th><th>URL (inside the Docker network)</th><th>Default</th></tr>"
        html_out += "".join(f"<tr><td>{esc(d['name'])}</td><td>{esc(d['type'])}</td><td>{esc(d['url'])}</td><td>{d['default']}</td></tr>" for d in info["datasources"]) + "</table>"
        html_out += "<h2>Provisioned dashboards</h2><p>Open through the owner's SSH tunnel (documentation/MONITORING-DEMO.md).</p><table><tr><th>Title</th><th>UID</th><th>Tunnel link</th></tr>"
        html_out += "".join(f"<tr><td>{esc(d['title'])}</td><td>{esc(d['uid'])}</td><td><a href='http://127.0.0.1:3000{esc(d['url'])}'>http://127.0.0.1:3000{esc(d['url'])}</a></td></tr>" for d in info["dashboards"]) + "</table>"
        html_out += "<h2>Dashboard panel data</h2><p>Drawn from Prometheus <code>query_range</code> (last 15 minutes, 30 s step) using the same PromQL as the dashboard panels. This is <strong>not</strong> a Grafana screenshot.</p>"
        html_out += "".join(svg_chart(title, item["series"], esc) for title, item in evidence["panel_data"].items())
    return html_out


def parse_xml(path):
    """Parse build-tool XML after rejecting entity declarations and dropping the DOCTYPE line."""
    text = Path(path).read_text(encoding="utf-8")
    if "<!ENTITY" in text.upper():
        raise ValueError(f"{path}: XML entity declarations are rejected")
    return ET.fromstring(re.sub(r"<!DOCTYPE[^>]*>", "", text))


def command_records(section):
    records = []
    for path in sorted(section.glob("*-result.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if {"check", "status", "exit_code", "finished_utc"} <= record.keys():
            records.append(record)
    return records


def read_facts(section):
    facts = {}
    for path in sorted(section.glob("*-facts.json")):
        facts.update(json.loads(path.read_text(encoding="utf-8")).get("facts", {}))
    return facts


def stage_status(folder, name):
    section = folder / name
    if name == "acceptance" and (section / "acceptance-result.json").is_file():
        return json.loads((section / "acceptance-result.json").read_text(encoding="utf-8")).get("status", "unavailable")
    if name in EVIDENCE_STAGES and read_evidence(folder, name):
        return evidence_status(read_evidence(folder, name), EVIDENCE_STAGES[name])
    if not section.is_dir():
        return "not run in this snapshot"
    records = command_records(section)
    if not records:
        return "facts only" if read_facts(section) else "not run in this snapshot"
    return "failed" if any(r["status"] != "passed" for r in records) else "passed"


def read_log(section, name):
    path = section / f"{name}.log"
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", path.read_text(encoding="utf-8")) if path.is_file() else ""


def build_measurements(folder):
    section = folder / "build"
    lines = []
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    suites = sorted(section.glob("surefire-reports/TEST-*.xml"))
    for suite in suites:
        node = parse_xml(suite)
        for key in totals:
            totals[key] += int(node.get(key, 0))
    if suites:
        lines.append(f"Surefire: {totals['tests']} tests in {len(suites)} classes, {totals['failures']} failures, "
                     f"{totals['errors']} errors, {totals['skipped']} skipped")
    jacoco = section / "jacoco/jacoco.xml"
    if jacoco.is_file():
        root = parse_xml(jacoco)
        for counter in root.findall("counter"):
            if counter.get("type") in ("LINE", "BRANCH"):
                covered, missed = int(counter.get("covered")), int(counter.get("missed"))
                total = covered + missed
                percent = f"{100 * covered / total:.1f}%" if total else "n/a"
                lines.append(f"JaCoCo {counter.get('type').lower()} coverage: {percent} ({covered}/{total})")
    return lines


def quality_measurements(folder):
    section = folder / "quality"
    log = read_log(section, "sonar")
    lines, links = [], []
    gate = re.search(r"QUALITY GATE STATUS: (\w+)", log)
    if gate:
        lines.append(f"SonarQube quality gate: {gate.group(1)}")
    dashboard = re.search(r"View details on (https?://\S+)", log)
    task = section / "report-task.txt"
    if task.is_file():
        values = dict(line.split("=", 1) for line in task.read_text(encoding="utf-8").splitlines() if "=" in line)
        dashboard_url = values.get("dashboardUrl") or (dashboard.group(1) if dashboard else None)
        if values.get("projectKey"):
            lines.append(f"SonarQube project: {values['projectKey']}")
    else:
        dashboard_url = dashboard.group(1) if dashboard else None
    if dashboard_url:
        links.append(("SonarQube dashboard", dashboard_url))
    return lines, links


def image_measurements(folder):
    path = folder / "image/trivy-image.json"
    if not path.is_file():
        return []
    report = json.loads(path.read_text(encoding="utf-8"))
    counts = {}
    for result in report.get("Results", []):
        for vulnerability in result.get("Vulnerabilities") or []:
            counts[vulnerability.get("Severity", "UNKNOWN")] = counts.get(vulnerability.get("Severity", "UNKNOWN"), 0) + 1
    targets = [r.get("Target", "") for r in report.get("Results", [])]
    return [f"Trivy image scan of {report.get('ArtifactName', 'the image')}: {counts.get('CRITICAL', 0)} CRITICAL, "
            f"{counts.get('HIGH', 0)} HIGH findings across {len(targets)} scanned targets"]


def render(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    esc = html.escape
    rows = []
    for path in sorted(folder.rglob("*-result.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        # Nmap's acceptance-result.json is an assessment, not a captured command.
        if not {"check", "status", "exit_code", "finished_utc"} <= result.keys():
            continue
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
    measurements = {name: [] for name, _, _ in STAGES}
    links = []
    measurements["build"] = build_measurements(folder)
    measurements["quality"], quality_links = quality_measurements(folder)
    links += quality_links
    measurements["image"] = image_measurements(folder)
    measurements.update(monitoring_measurements(folder))
    dependabot = read_evidence(folder, "dependabot")
    measurements["dependabot"] = dependabot.get("summary", []) if dependabot else []
    for name in ("artifact", "registry", "deploy", "monitoring"):
        facts = read_facts(folder / name)
        for key in ("match", "snapshot_version", "image", "digest"):
            if key in facts:
                measurements[name].append(f"{key}: {facts[key]}")
    artifact_facts = read_facts(folder / "artifact")
    if artifact_facts.get("repository_url"):
        parsed = urlparse(artifact_facts["repository_url"])
        repository = re.search(r"/repository/([^/]+)/", parsed.path)
        if repository:
            links.append(("Nexus repository browser", f"{parsed.scheme}://{parsed.netloc}/#browse/browse:{repository.group(1)}"))
    # A disposable runner's 127.0.0.1 tools are gone after the run: keep only links a reader can still open.
    links = [(label, url) for label, url in links if urlparse(url).hostname not in ("127.0.0.1", "localhost")]
    for name in ("build", "quality", "artifact", "image", "registry", "deploy", "monitoring"):
        stats += measurements[name]
    stats += [f"Prometheus: {line}" for line in measurements["prometheus"]]
    stats += [f"Grafana: {line}" for line in measurements["grafana"]]
    stats += [f"Dependabot: {line}" for line in measurements["dependabot"]]
    acceptance = folder / "acceptance"
    nmap_path = acceptance / "acceptance-result.json"
    nmap = json.loads(nmap_path.read_text(encoding="utf-8")) if nmap_path.is_file() else None
    if nmap:
        profiles = [p for view in nmap.get("results", []) for p in view.get("profiles", [])]
        stats.append(f"Nmap acceptance: {nmap.get('status', 'unavailable')}; {len(profiles)} scan profiles; {sum(len(p.get('unexpected_open', [])) for p in profiles)} unexpected open-port observations")
        if (acceptance / "index.html").is_file():
            (acceptance / "report.html").write_text((acceptance / "index.html").read_text(encoding="utf-8"), encoding="utf-8")
    run = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
    head = os.environ.get("GITHUB_SHA", "local")
    files = [p for p in sorted(folder.rglob("*")) if p.is_file() and p.name != "index.html"]
    body = """<!doctype html><html lang="en"><meta charset="utf-8"><title>DevSecOps security reports</title>
<style>body{font:17px/1.5 Arial,sans-serif;color:#172332;max-width:1100px;margin:40px auto;padding:0 24px}h1{font-size:32px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:10px;text-align:left}th{background:#eef3f7}a{color:#075e91}code{overflow-wrap:anywhere}li{margin:8px 0}.passed{color:#116329;font-weight:bold}.failed{color:#a40e26;font-weight:bold}.skip{color:#6a737d}.attention{color:#9a6700;font-weight:bold}.banner{background:#fff8c5;border:1px solid #d4a72c;padding:12px 16px}@media print{body{margin:0;font-size:12px}a{color:inherit}}</style>"""
    body += f"<h1>DevSecOps security reports</h1><p>Report execution revision: <code>{esc(head)}</code><br>Run: <a href='{esc(run)}'>{esc(run)}</a></p>"
    body += "<p>Order: checkout, local-hook replay and commit security gates before Maven compilation; Nmap acceptance after deployment. Each original record retains its own execution time and provenance. Threat modeling remains a human review activity.</p>"
    body += "<h2>Pipeline stages at a glance</h2><table><tr><th>Stage</th><th>Tool</th><th>Outcome</th><th>What it measured</th><th>Report</th></tr>"
    summary_rows = []
    for name, title, tools in STAGES:
        status = stage_status(folder, name)
        css = status if status in ("passed", "failed", "attention") else "skip"
        if status == "not run in this snapshot":
            measured = ""  # Never describe measurements for a stage that left no evidence.
        elif name == "acceptance":
            measured = "; ".join(s for s in stats if s.startswith("Nmap"))
        elif name == "precommit":
            measured = "hook transcript and threat model"
        elif name == "sast":
            measured = "; ".join(s for s in stats if s.startswith("Semgrep"))
        elif name == "iac":
            measured = "; ".join(s for s in stats if s.startswith("checkov"))
        elif name == "dependencies":
            measured = f"{package_count} packages analyzed" if package_count != "not available" else ""
        elif name == "secrets":
            measured = "full available Git history"
        else:
            measured = "; ".join(measurements[name])
        has_page = (folder / name).is_dir()
        link = f"<a href='{name}/report.html'>Open</a>" if has_page else "-"
        body += f"<tr><td>{esc(title)}</td><td>{esc(tools)}</td><td class='{css}'>{esc(status)}</td><td>{esc(measured or '-')}</td><td>{link}</td></tr>"
        summary_rows.append(f"| {title} | {tools} | {status} | {measured or '-'} |")
    body += "</table>"
    shots = sorted((folder / "screenshots").glob("*.png"))
    if shots:
        body += ("<h2>Screenshots of the live tools, captured by this run</h2><p>Taken with headless Chrome inside the "
                 "disposable runner, of its own SonarQube, Nexus, Grafana, Prometheus and API (127.0.0.1 only).</p>")
        body += "".join(f"<figure style='margin:18px 0'><a href='screenshots/{esc(p.name)}'><img src='screenshots/{esc(p.name)}' "
                        f"alt='{esc(p.stem)}' style='max-width:100%;border:1px solid #bbb'></a><figcaption>{esc(p.stem.replace('-', ' '))}"
                        "</figcaption></figure>" for p in shots)
    if links:
        body += "<h2>Live tool dashboards for this run</h2><ul>" + "".join(f"<li><a href='{esc(url)}'>{esc(label)}</a> (sign-in required)</li>" for label, url in links) + "</ul>"
    body += "<p>Grafana (<code>http://127.0.0.1:3000/d/student-devsecops</code>, <code>/d/student-vms</code>) and Prometheus (<code>http://127.0.0.1:9091/targets</code>) are private: open them through the owner's SSH tunnel described in documentation/MONITORING-DEMO.md.</p>"
    if jobs:
        body += "<h2>Security job outcomes</h2><ul>" + "".join(f"<li>{esc(name)}: {esc(value['result'])}</li>" for name, value in jobs.items()) + "</ul>"
    body += "<h2>Scanner measurements</h2><ul>" + "".join(f"<li>{esc(s)}</li>" for s in stats) + "</ul>"
    body += "<h2>Acceptance phase: Nmap</h2>"
    if nmap:
        body += f"<p>Recorded acceptance result: <strong>{esc(nmap.get('status', 'unavailable'))}</strong>. <a href='acceptance/report.html'>Open the Nmap report</a> / <a href='acceptance/acceptance-result.json'>Original assessment JSON</a>.</p>"
        body += "<p>This is a scoped TCP exposure check. Filtered is distinct from closed; service names can be port-table guesses. Missing/incomplete scans cannot establish a passed assessment. Earlier failed attempts remain historical evidence.</p>"
        body += "<table><tr><th>Viewpoint / profile</th><th>Target</th><th>TCP ports scanned</th><th>Open ports</th><th>Result</th></tr>"
        for view in nmap.get("results", []):
            for profile in view.get("profiles", []):
                values = [view.get("view", "") + " / " + profile["name"], profile["target"],
                          profile.get("ports_scanned", "incomplete"), str(profile.get("open_ports", "not determined")), profile["status"]]
                body += "<tr>" + "".join(f"<td>{esc(str(value))}</td>" for value in values) + "</tr>"
        body += "</table>"
        for view in nmap.get("results", []):
            body += f"<p>{esc(view.get('view', ''))} scan: {esc(view.get('started_utc', 'time not recorded'))} to {esc(view.get('finished_utc', 'time not recorded'))} UTC.</p>"
    else:
        body += "<p>Nmap acceptance is not available in this snapshot. A pre-build report is generated before deployment, so it cannot contain a later acceptance scan. The final coursework report combines the phases when their artifacts exist.</p>"
    body += "<h2>Actual command outcomes</h2><table><tr><th>Check</th><th>Result</th><th>Exit</th><th>Finished UTC</th><th>Original record</th></tr>"
    for check, status, code, finished, record in rows:
        body += f"<tr><td>{esc(check)}</td><td>{esc(status)}</td><td>{esc(code)}</td><td>{esc(finished)}</td><td><a href='{esc(record)}'>JSON record</a></td></tr>"
    body += "</table><p>Missing results mean a command did not finish or did not run. CI history scanning complements local staged-secret hooks. Controlled exercises use temporary fixtures and are separate from application findings. The source POM scan excludes test and optional dependencies. Checkov skipped policies remain listed in the raw reports and documented configuration.</p>"
    body += "<h2>Downloadable original reports and logs</h2><ul>" + "".join(f"<li><a href='{esc(p.relative_to(folder).as_posix())}'>{esc(p.relative_to(folder).as_posix())}</a></li>" for p in files) + "</ul></html>"
    (folder / "index.html").write_text(body, encoding="utf-8")
    for name, title, tools in STAGES:
        section = folder / name
        if name == "acceptance" or not section.is_dir():
            continue
        page = body[:body.index("<h1>")]
        page += f"<h1>{esc(title)}: original evidence</h1><p>Tool: {esc(tools)}<br>Revision: <code>{esc(head)}</code><br><a href='{esc(run)}'>Actions run</a> / <a href='../index.html'>All stages</a></p>"
        page += "<p>This page renders the original tool transcripts and recorded facts. It is an assessment report, not a separate vendor dashboard.</p>"
        if name == "dependencies" and inventory.exists():
            page += "<h2>Verified inventory</h2><pre>" + esc(json.dumps(details, indent=2)) + "</pre>"
        if name == "iac":
            page += "<h2>Policy counts</h2><ul>" + "".join(f"<li>{esc(s)}</li>" for s in stats if s.startswith("checkov")) + "</ul>"
        if measurements.get(name):
            page += "<h2>Measured by this stage</h2><ul>" + "".join(f"<li>{esc(s)}</li>" for s in measurements[name]) + "</ul>"
        page += monitoring_page(name, folder, esc) if name in ("prometheus", "grafana") else ""
        page += dependabot_page(folder, esc) if name == "dependabot" else ""
        facts = read_facts(section)
        if facts:
            page += "<h2>Recorded facts</h2><table>" + "".join(f"<tr><th>{esc(k)}</th><td><code>{esc(v)}</code></td></tr>" for k, v in facts.items()) + "</table>"
        for outcome in sorted(section.glob("*-result.json")):
            record = json.loads(outcome.read_text())
            if "check" not in record:
                continue
            page += f"<h2>{esc(record['check'])}: {esc(record['status'])}</h2><p>Exit {record['exit_code']}. Started {esc(record.get('started_utc', 'not recorded'))}; finished {esc(record['finished_utc'])}</p>"
        for log in sorted(section.glob("*.log")):
            transcript = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", log.read_text(encoding="utf-8"))
            page += f"<h2>{esc(log.name)}</h2><pre style='white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:18px'>{esc(transcript)}</pre>"
        if name == "precommit":
            page += "<p>The STRIDE threat model is preserved as THREAT-MODEL.md. It remains a human review activity.</p>"
        page += "</html>"
        (section / "report.html").write_text(page, encoding="utf-8")
    summary = "## DevSecOps security reports\n\n" + "\n".join(f"- {name}: **{value['result']}**" for name, value in jobs.items())
    summary += "\n\n### Pipeline stages\n\n| Stage | Tool | Outcome | What it measured |\n| --- | --- | --- | --- |\n" + "\n".join(summary_rows)
    summary += "\n\n" + "\n".join(f"- {s}" for s in stats)
    later = nmap or any((folder / name).is_dir() for name in LATER_STAGES)
    artifact = os.environ.get("SECURITY_REPORT_ARTIFACT") or ("devsecops-security-reports" if later else "professor-security-reports")
    summary += f"\n\nDownload **{artifact}** and open **index.html** for the original reports, logs and available phase assessments.\n"
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as stream:
            stream.write(summary)
    (folder / "README.md").write_text(summary, encoding="utf-8")
    print(f"Readable report written to {folder / 'index.html'}")


if __name__ == "__main__":
    render(sys.argv[1])
