"""Generate the separate Azure host dashboard; Java metrics keep their own dashboard."""
import json
from pathlib import Path

queries = [
    ("Node Exporter scrape availability", 'up{job="azure-nodes"}', "short", "1 means the exporter scrape succeeded; it does not verify SonarQube or Nexus health."),
    ("VM CPU usage", '100 * (1 - avg by (host) (rate(node_cpu_seconds_total{job="azure-nodes",mode="idle"}[2m])))', "percent", "Host CPU utilization averaged across CPU cores."),
    ("VM RAM usage", '100 * (1 - node_memory_MemAvailable_bytes{job="azure-nodes"} / node_memory_MemTotal_bytes{job="azure-nodes"})', "percent", "Host memory in use, based on Linux MemAvailable (includes reclaimable cache)."),
    ("Root filesystem usage", '100 * (1 - node_filesystem_avail_bytes{job="azure-nodes",mountpoint="/",fstype!~"tmpfs|overlay|squashfs"} / node_filesystem_size_bytes{job="azure-nodes",mountpoint="/",fstype!~"tmpfs|overlay|squashfs"})', "percent", "Root filesystem capacity unavailable to non-root users; reserved blocks are included."),
    ("VM network receive", 'sum by (host) (rate(node_network_receive_bytes_total{job="azure-nodes",device!~"lo|docker.*|veth.*|br-.*"}[2m]))', "Bps", "Network receive rate, excluding loopback and Docker bridges/veth interfaces."),
    ("VM network transmit", 'sum by (host) (rate(node_network_transmit_bytes_total{job="azure-nodes",device!~"lo|docker.*|veth.*|br-.*"}[2m]))', "Bps", "Network transmit rate, excluding loopback and Docker bridges/veth interfaces."),
    ("VM disk read + write", 'sum by (host) (rate(node_disk_read_bytes_total{job="azure-nodes",device!~"loop.*|ram.*|fd.*|sr.*|dm-.*"}[2m]) + rate(node_disk_written_bytes_total{job="azure-nodes",device!~"loop.*|ram.*|fd.*|sr.*|dm-.*"}[2m]))', "Bps", "Combined disk read/write throughput across the VM's non-virtual block devices."),
    ("VM uptime", 'time() - node_boot_time_seconds{job="azure-nodes"}', "s", "Time since the Linux host booted."),
]
panels = []
for index, (title, expression, unit, description) in enumerate(queries):
    panels.append({
        "id": index + 1, "title": title, "description": description, "type": "timeseries",
        "gridPos": {"x": index % 2 * 12, "y": index // 2 * 8, "w": 12, "h": 8},
        "datasource": {"type": "prometheus", "uid": "prometheus"},
        "targets": [{"refId": "A", "expr": expression, "legendFormat": "{{host}}"}],
        "fieldConfig": {"defaults": {"unit": unit, "min": 0}, "overrides": []},
        "options": {"legend": {"displayMode": "list", "placement": "bottom", "calcs": ["lastNotNull"]}},
    })
dashboard = {
    "uid": "student-vms", "title": "Azure VMs - Node Exporter", "schemaVersion": 41,
    "version": 1, "refresh": "10s", "time": {"from": "now-15m", "to": "now"},
    "tags": ["azure", "node-exporter", "host-monitoring"], "panels": panels,
}
(Path(__file__).resolve().parents[1] / "monitoring/node-dashboard.json").write_text(
    json.dumps(dashboard, indent=2) + "\n", encoding="utf-8")
