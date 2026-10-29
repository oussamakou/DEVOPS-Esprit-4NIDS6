"""Verify real Prometheus scrape health and host metrics for both Azure VMs."""
import argparse
import json
import urllib.parse
import urllib.request

HOSTS = {"application-vm", "tools-vm"}


def query(base, expression):
    url = base.rstrip("/") + "/api/v1/query?" + urllib.parse.urlencode({"query": expression})
    with urllib.request.urlopen(url, timeout=15) as response:
        data = json.load(response)
    if data["status"] != "success":
        raise RuntimeError("Prometheus query failed")
    return data["data"]["result"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:9091")
    args = parser.parse_args()
    checks = {
        "Exporter scrape UP": 'up{job="azure-nodes"}',
        "Linux host identity": 'node_uname_info{job="azure-nodes"}',
        "CPU cores": 'count by (host) (node_cpu_seconds_total{job="azure-nodes",mode="idle"})',
        "RAM total bytes": 'node_memory_MemTotal_bytes{job="azure-nodes"}',
        "Root filesystem bytes": 'node_filesystem_size_bytes{job="azure-nodes",mountpoint="/",fstype!~"tmpfs|overlay|squashfs"}',
        "Host network receive counters": 'sum by (host) (node_network_receive_bytes_total{job="azure-nodes",device!~"lo|docker.*|veth.*|br-.*"})',
        "CPU busy percent (needs two scrapes)": '100 * (1 - avg by (host) (rate(node_cpu_seconds_total{job="azure-nodes",mode="idle"}[2m])))',
    }
    app = query(args.url, 'up{job="student-api"}')
    if len(app) != 1 or float(app[0]["value"][1]) != 1:
        raise RuntimeError("Application scrape must remain UP")
    print("Application scrape remains UP")
    for title, expression in checks.items():
        result = query(args.url, expression)
        if {item["metric"].get("host") for item in result} != HOSTS:
            raise RuntimeError(f"{title}: expected live data from both VMs")
        if title == "Exporter scrape UP" and any(float(item["value"][1]) != 1 for item in result):
            raise RuntimeError("A Node Exporter target is DOWN")
        for item in result:
            print(f"{title}: {item['metric']['host']} = {item['value'][1]}")
    print("NODE_MONITORING_VERIFIED: both Azure hosts and application UP")


if __name__ == "__main__":
    main()
