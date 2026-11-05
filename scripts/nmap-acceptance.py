"""Bounded TCP acceptance scans of the owned Azure lab; retain original Nmap files."""
import argparse
from datetime import datetime, timezone
import hashlib
import html
import ipaddress
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def policy_hash(policy):
    # Stable across Windows CRLF and Linux LF checkouts.
    return hashlib.sha256(json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def expand_ports(expression):
    ports = set()
    for part in expression.split(","):
        if not re.fullmatch(r"\d+(?:-\d+)?", part):
            raise ValueError("Invalid TCP port expression")
        bounds = [int(x) for x in part.split("-")]
        first, last = bounds[0], bounds[-1]
        if not 1 <= first <= last <= 65535:
            raise ValueError("Invalid TCP port range")
        ports.update(range(first, last + 1))
    return ports


def load_policy(path):
    policy = json.loads(Path(path).read_text(encoding="utf-8"))
    scanned = expand_ports(policy["ports"])
    if policy.get("version") != 1 or set(policy["profiles"]) != {"public", "private"}:
        raise ValueError("Unsupported acceptance policy")
    names = set()
    for profiles in policy["profiles"].values():
        if not profiles:
            raise ValueError("A scan viewpoint has no targets")
        for profile in profiles:
            ipaddress.IPv4Address(profile["target"])
            name = profile["name"]
            if not re.fullmatch(r"[a-z]+(?:-[a-z]+)*", name) or name in names:
                raise ValueError("Invalid or duplicate scan profile name")
            names.add(name)
            allowed, required = set(profile["allowed_open"]), set(profile["required_open"])
            if not required <= allowed <= scanned:
                raise ValueError("Expected open ports must be in the scanned policy scope")
    return policy


def assess_xml(path, profile, ports):
    """Fail closed on incomplete scans, incorrect targets or policy violations."""
    if Path(path).stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Nmap XML exceeds the report limit")
    root = ET.parse(path).getroot()
    finished = root.find("runstats/finished")
    if root.tag != "nmaprun" or root.get("scanner") != "nmap" or finished is None or finished.get("exit") != "success":
        raise ValueError("Nmap did not report a successful completed scan")
    scan = root.findall("scaninfo")
    expected = expand_ports(ports)
    if len(scan) != 1 or scan[0].get("type") != "connect" or scan[0].get("protocol") != "tcp" or expand_ports(scan[0].get("services", "")) != expected or int(scan[0].get("numservices", 0)) != len(expected):
        raise ValueError("Nmap coverage does not match the requested TCP ports")
    hosts = root.findall("host")
    if len(hosts) != 1 or hosts[0].find("status") is None or hosts[0].find("status").get("state") != "up":
        raise ValueError("Target scan is absent, down or timed out")
    host = hosts[0]
    if host.get("timedout") == "true":
        raise ValueError("Nmap host timeout: scan coverage is incomplete")
    if [a.get("addr") for a in host.findall("address") if a.get("addrtype") == "ipv4"] != [profile["target"]]:
        raise ValueError("XML target differs from the authorized policy target")
    observations, explicit = [], set()
    for port in host.findall("ports/port"):
        number = int(port.get("portid", 0))
        state = port.find("state")
        if number not in expected or number in explicit or port.get("protocol") != "tcp" or state is None or state.get("state") not in ("open", "closed", "filtered"):
            raise ValueError("Unexpected, duplicate or ambiguous port result")
        explicit.add(number)
        service = port.find("service")
        observations.append({"port": number, "state": state.get("state"), "reason": state.get("reason", ""),
                             "service": dict(service.attrib) if service is not None else {}})
    aggregate = host.findall("ports/extraports")
    if any(item.get("state") not in ("closed", "filtered") for item in aggregate):
        raise ValueError("Ambiguous or unenumerated open-port results")
    if len(explicit) + sum(int(item.get("count", 0)) for item in aggregate) != len(expected):
        raise ValueError("Incomplete scan: not all policy ports have a result")
    opened = {item["port"] for item in observations if item["state"] == "open"}
    unexpected = sorted(opened - set(profile["allowed_open"]))
    missing = sorted(set(profile["required_open"]) - opened)
    return {"name": profile["name"], "target": profile["target"], "status": "failed" if unexpected or missing else "passed",
            "open_ports": sorted(opened), "unexpected_open": unexpected, "missing_required": missing,
            "ports_scanned": len(expected), "observations": observations,
            "aggregate_states": [dict(item.attrib) for item in aggregate]}


def run_view(view, output, policy_path=ROOT / "security/nmap-policy.json"):
    policy = load_policy(policy_path)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    result = {"view": view, "started_utc": datetime.now(timezone.utc).isoformat(), "scanner_host": socket.gethostname(),
              "policy_sha256": policy_hash(policy), "ports": policy["ports"], "profiles": []}
    try:
        if view == "private" and socket.gethostname().split(".")[0] != policy["private_scanner_hostname"]:
            raise ValueError("Run private/loopback acceptance on the policy's application VM")
        binary = shutil.which("nmap")
        if not binary:
            raise RuntimeError("Nmap is not installed; install the operating system's nmap package")
        version = subprocess.run([binary, "--version"], capture_output=True, text=True, check=True, timeout=15).stdout
        (output / "nmap-version.txt").write_text(version, encoding="utf-8")
        for profile in policy["profiles"][view]:
            prefix = output / profile["name"]
            command = [binary, "--unprivileged", "-sT", "-Pn", "-n", "-sV", "--version-light", "--reason", "-T3",
                       "--max-rate", "100", "--min-parallelism", "16", "--max-parallelism", "32",
                       "--initial-rtt-timeout", "500ms", "--max-rtt-timeout", "1s",
                       "--max-retries", "1", "--host-timeout", "180s", "--no-stylesheet",
                       "-p", policy["ports"], "-oA", str(prefix), profile["target"]]
            item = {"name": profile["name"], "target": profile["target"], "command": command, "status": "error"}
            try:
                completed = subprocess.run(command, capture_output=True, text=True, timeout=210)
                (output / f"{profile['name']}.log").write_text(completed.stdout + completed.stderr, encoding="utf-8")
                if completed.returncode != 0:
                    raise RuntimeError(f"Nmap exited {completed.returncode}; inspect the original log")
                item.update(assess_xml(prefix.with_suffix(".xml"), profile, policy["ports"]))
            except (OSError, RuntimeError, ValueError, ET.ParseError, subprocess.SubprocessError) as error:
                item["error"] = str(error)
            result["profiles"].append(item)
        result["status"] = "passed" if len(result["profiles"]) == len(policy["profiles"][view]) and all(p["status"] == "passed" for p in result["profiles"]) else "failed"
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        result.update(status="error", error=str(error))
    result["finished_utc"] = datetime.now(timezone.utc).isoformat()
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def combine(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    policy = load_policy(ROOT / "security/nmap-policy.json")
    results, sections = [], []
    for view in ("public", "private"):
        path = folder / view / "result.json"
        result = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"view": view, "status": "error", "error": "No scan result was produced", "profiles": []}
        expected = {p["name"]: p for p in policy["profiles"][view]}
        if result.get("view") != view or result.get("policy_sha256") != policy_hash(policy) or len(result.get("profiles", [])) != len(expected) or {p.get("name") for p in result.get("profiles", [])} != set(expected):
            result.update(status="error", error="Missing profiles or scan policy identity mismatch", profiles=[])
        else:
            for item in result["profiles"]:
                try:
                    name = item["name"]
                    if not (folder / view / f"{name}.nmap").is_file() or not (folder / view / "nmap-version.txt").is_file():
                        raise ValueError("Original Nmap text/version report is missing")
                    assessment = assess_xml(folder / view / f"{name}.xml", expected[name], policy["ports"])
                    item.update(assessment)
                except (OSError, ValueError, ET.ParseError) as error:
                    item.update(status="error", error=str(error))
            if result.get("status") != "passed" or any(p["status"] != "passed" for p in result["profiles"]):
                result["status"] = "failed"
        results.append(result)
        sections.append(f'<h2>{view.title()} viewpoint: {html.escape(result["status"])}</h2>')
        if result.get("error"):
            sections.append('<p>' + html.escape(result["error"]) + '</p>')
        for item in result["profiles"]:
            name = item["name"]
            sections.append(f'<section><h3>{html.escape(name)} — {html.escape(item["target"])} — {html.escape(item["status"])}</h3>')
            sections.append('<p>Open TCP ports: ' + html.escape(str(item.get("open_ports", []))) + '; unexpected: ' + html.escape(str(item.get("unexpected_open", []))) + '; missing required: ' + html.escape(str(item.get("missing_required", []))) + '</p>')
            if item.get("error"):
                sections.append('<p>' + html.escape(item["error"]) + '</p>')
            sections.append(f'<p>Original reports: <a href="{view}/{name}.xml">Nmap XML</a> · <a href="{view}/{name}.nmap">Nmap text</a> · <a href="{view}/{name}.log">console log</a></p>')
            sections.append('<table><tr><th>TCP port</th><th>State</th><th>Service observation</th></tr>')
            for port in item.get("observations", []):
                service = ' '.join(port["service"].get(key, '') for key in ("name", "product", "version")).strip()
                sections.append(f'<tr><td>{port["port"]}</td><td>{html.escape(port["state"])}</td><td>{html.escape(service)}</td></tr>')
            sections.append('</table></section>')
    passed = all(r.get("status") == "passed" for r in results)
    summary = {"status": "passed" if passed else "failed", "results": results}
    (folder / "acceptance-result.json").write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    (folder / "index.html").write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><title>Nmap acceptance reports</title>
<style>body{font:16px system-ui;margin:32px;max-width:1150px;color:#18283b}section{border:1px solid #bbb;padding:16px;margin:18px 0}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:6px;text-align:left}a{color:#1450a0}</style>
<h1>Nmap acceptance: ''' + summary["status"].upper() + '''</h1>
<p>Owned studentcourse Azure lab. TCP connect scans with light service detection; no exploit scripts.</p>
<p>Coverage: ''' + html.escape(policy["ports"]) + '''. Ports outside this list and UDP were not tested.
Filtered means probes received no usable response from this viewpoint. A service version is an observation, not proof of a vulnerability.</p>
<p>External runner: only tools HTTPS ports 443/8443 may be open; SSH is owner-only. Internal application-VM scans verify the private exporters and localhost application/monitoring endpoints.
Required open ports provide positive controls; incomplete scans and missing reports fail acceptance.</p>''' + ''.join(sections) + '</html>', encoding='utf-8')
    return passed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan")
    scan.add_argument("--view", choices=("public", "private"), required=True)
    scan.add_argument("--output", required=True)
    collect = commands.add_parser("combine")
    collect.add_argument("--reports", required=True)
    args = parser.parse_args()
    if args.command == "scan":
        result = run_view(args.view, args.output)
        print(f"NMAP_ACCEPTANCE {args.view}: {result['status']}")
        for item in result["profiles"]:
            print(f"  {item['name']}: {item['status']}, open={item.get('open_ports', [])}, unexpected={item.get('unexpected_open', [])}, missing={item.get('missing_required', [])}")
        sys.exit(0 if result["status"] == "passed" else 1)
    passed = combine(args.reports)
    print('NMAP_ACCEPTANCE ' + ('PASSED' if passed else 'FAILED') + ': open the standalone index.html')
    sys.exit(0 if passed else 1)
