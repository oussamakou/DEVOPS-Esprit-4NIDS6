"""Azure guest helper: sample Prometheus and Grafana, keep the evidence, return checksummed chunks.

Runs as root on the application VM through Azure Run Command (python3 standard
library only). The Grafana admin password is read from the VM's root-only .env
and sent only as a Basic-auth header to 127.0.0.1; it is never printed or stored
in the evidence. Azure keeps only the last ~4 KB of stdout, so the evidence is
zipped and returned in small chunks that the runner reassembles and verifies.
"""
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
import uuid
import zipfile

STORE = Path("/opt/student-course/evidence/monitoring")
ENV_FILE = Path("/opt/student-course/.env")
CHUNK = 3000  # Includes <250 bytes of metadata; fits Azure's 4096-byte stdout tail.
PROMETHEUS = "http://127.0.0.1:9091"
GRAFANA = "http://127.0.0.1:3000"
API = "http://127.0.0.1:8089/student/students/getAllStudents"

APP = 'application="student-management"'
NODE_FS = 'job="azure-nodes",mountpoint="/",fstype!~"tmpfs|overlay|squashfs"'
INSTANT = {
    "API scrape availability": 'up{job="student-api"}',
    "Requests per second": f'sum(rate(http_server_requests_seconds_count{{{APP},uri!~"/actuator.*"}}[5m]))',
    "5xx responses per second": f'sum(rate(http_server_requests_seconds_count{{{APP},status=~"5.."}}[5m]))',
    "95th percentile latency (s)": f'histogram_quantile(0.95, sum by (le) (rate(http_server_requests_seconds_bucket{{{APP},uri!~"/actuator.*"}}[5m])))',
    "JVM heap bytes": f'sum(jvm_memory_used_bytes{{{APP},area="heap"}})',
    "Java process CPU": f'process_cpu_usage{{{APP}}}',
    "Host exporter scrape UP": 'up{job="azure-nodes"}',
    "Host CPU busy %": '100 * (1 - avg by (host) (rate(node_cpu_seconds_total{job="azure-nodes",mode="idle"}[2m])))',
    "Host memory used %": '100 * (1 - node_memory_MemAvailable_bytes{job="azure-nodes"} / node_memory_MemTotal_bytes{job="azure-nodes"})',
    "Host root filesystem used %": f'100 * (1 - node_filesystem_avail_bytes{{{NODE_FS}}} / node_filesystem_size_bytes{{{NODE_FS}}})',
}
RANGES = ["Requests per second", "95th percentile latency (s)", "JVM heap bytes", "Java process CPU",
          "Host CPU busy %", "Host memory used %"]
EXPECTED_DASHBOARDS = {"student-devsecops", "student-vms"}


def get_json(url, params=None, auth=None, timeout=20):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {"User-Agent": "student-devsecops-evidence"}
    if auth:
        headers["Authorization"] = "Basic " + base64.b64encode(f"admin:{auth}".encode()).decode()
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
        return json.load(response)


def number(value):
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    return round(converted, 6) if math.isfinite(converted) else None


def grafana_password(env_file=ENV_FILE):
    for line in Path(env_file).read_text(encoding="utf-8").splitlines():
        if line.startswith("GRAFANA_PASSWORD="):
            return line.split("=", 1)[1].strip()
    raise ValueError("GRAFANA_PASSWORD is missing from the runtime .env")


def generate_traffic(api, count, pause):
    ok = 0
    for _ in range(count):
        try:
            with urllib.request.urlopen(api, timeout=10) as response:
                ok += 1 if response.status == 200 else 0
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(pause)
    return {"endpoint": "GET /student/students/getAllStudents (read-only)", "requests": count, "succeeded": ok}


def instant(prometheus, expression):
    data = get_json(prometheus + "/api/v1/query", {"query": expression})["data"]["result"]
    return [{"metric": item["metric"], "value": number(item["value"][1])} for item in data]


def ranged(prometheus, expression, now, minutes=15, step=30):
    data = get_json(prometheus + "/api/v1/query_range", {"query": expression, "start": int(now - minutes * 60),
                                                         "end": int(now), "step": step})["data"]["result"]
    return [{"metric": item["metric"], "values": [[int(t), number(v)] for t, v in item["values"]]} for item in data]


def collect(prometheus=PROMETHEUS, grafana=GRAFANA, api=API, env_file=ENV_FILE, traffic=30, pause=1.0, settle=20):
    evidence = {"generated_utc": datetime.now(timezone.utc).isoformat(), "checks": []}
    evidence["traffic"] = generate_traffic(api, traffic, pause)
    time.sleep(settle)  # Prometheus scrapes every 15 s; allow at least one scrape after the traffic.
    now = time.time()
    targets = get_json(prometheus + "/api/v1/targets")["data"]["activeTargets"]
    evidence["prometheus"] = {
        "targets": [{"job": t["labels"].get("job"), "instance": t["labels"].get("instance"), "host": t["labels"].get("host"),
                     "health": t["health"], "last_scrape": t.get("lastScrape"), "scrape_url": t.get("scrapeUrl"),
                     "last_error": t.get("lastError", "")} for t in targets],
        "instant": {name: {"expression": expr, "result": instant(prometheus, expr)} for name, expr in INSTANT.items()},
        "ranges": {name: {"expression": INSTANT[name], "series": ranged(prometheus, INSTANT[name], now)} for name in RANGES},
        "rule_groups": len(get_json(prometheus + "/api/v1/rules")["data"]["groups"]),
    }
    password = grafana_password(env_file)
    health = get_json(grafana + "/api/health")
    datasources = get_json(grafana + "/api/datasources", auth=password)
    dashboards = get_json(grafana + "/api/search", {"type": "dash-db"}, auth=password)
    evidence["grafana"] = {
        "health": health,
        "datasources": [{"name": d["name"], "type": d["type"], "url": d["url"], "default": d.get("isDefault", False)} for d in datasources],
        "dashboards": [{"title": d["title"], "uid": d["uid"], "url": d["url"]} for d in dashboards],
    }
    jobs = {}
    for target in evidence["prometheus"]["targets"]:
        jobs.setdefault(target["job"], []).append(target["health"])
    requests_series = evidence["prometheus"]["instant"]["Requests per second"]["result"]
    add = lambda name, ok, detail, required=True: evidence["checks"].append({"name": name, "ok": bool(ok), "detail": detail, "required": required})  # noqa: E731
    add("Prometheus student-api target UP", jobs.get("student-api") == ["up"], f"student-api: {jobs.get('student-api')}")
    add("Prometheus host exporter targets UP", bool(jobs.get("azure-nodes")) and set(jobs["azure-nodes"]) == {"up"},
        f"azure-nodes: {jobs.get('azure-nodes')}")
    add("Grafana database healthy", health.get("database") == "ok", f"health: {health}")
    add("Grafana Prometheus data source provisioned", any(d["type"] == "prometheus" for d in evidence["grafana"]["datasources"]),
        f"{len(datasources)} data source(s)")
    found = {d["uid"] for d in evidence["grafana"]["dashboards"]}
    add("Grafana dashboards provisioned", EXPECTED_DASHBOARDS <= found, f"found {sorted(found)}")
    add("Prometheus saw API request traffic", bool(requests_series) and (requests_series[0]["value"] or 0) > 0,
        f"{evidence['traffic']['succeeded']}/{evidence['traffic']['requests']} requests succeeded; rate series {len(requests_series)}",
        required=False)
    return evidence


def emit(identifier, index):
    if not re.fullmatch(r"[a-f0-9]{32}", identifier):
        raise ValueError("Invalid evidence identifier")
    payload = (STORE / identifier / "evidence.zip").read_bytes()
    encoded = base64.b64encode(payload).decode("ascii")
    count = (len(encoded) + CHUNK - 1) // CHUNK
    if not 0 <= index < count:
        raise ValueError("Invalid evidence chunk")
    message = {"id": identifier, "index": index, "chunks": count,
               "sha256": hashlib.sha256(payload).hexdigest(), "payload": encoded[index * CHUNK:(index + 1) * CHUNK]}
    print("MONITORING_EVIDENCE_V1 " + json.dumps(message, separators=(",", ":")))


def main():
    mode = sys.argv[1]
    if mode == "fetch":
        emit(sys.argv[2], int(sys.argv[3]))
        return
    if mode != "collect":
        raise ValueError("Expected collect or fetch")
    identifier = uuid.uuid4().hex
    destination = STORE / identifier
    destination.mkdir(mode=0o700, parents=True)
    evidence = collect()
    with zipfile.ZipFile(destination / "evidence.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("evidence.json", json.dumps(evidence, separators=(",", ":")))
    # Persist only this retrieval helper. It contains no credentials.
    (STORE / "fetch-evidence.py").write_bytes(Path(__file__).read_bytes())
    emit(identifier, 0)


if __name__ == "__main__":
    main()
