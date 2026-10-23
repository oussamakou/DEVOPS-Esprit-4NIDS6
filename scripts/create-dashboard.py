"""Regenerate the versioned Grafana dashboard ConfigMap using only Python stdlib."""
import json
from pathlib import Path

queries = [
    ("API scrape availability", 'up{job="student-api"}', "short"),
    ("Requests / second", 'sum(rate(http_server_requests_seconds_count{application="student-management",uri!~"/actuator.*"}[5m]))', "reqps"),
    ("5xx responses / second", 'sum(rate(http_server_requests_seconds_count{application="student-management",status=~"5.."}[5m]))', "reqps"),
    ("95th percentile request latency", 'histogram_quantile(0.95, sum by (le) (rate(http_server_requests_seconds_bucket{application="student-management",uri!~"/actuator.*"}[5m])))', "s"),
    ("JVM heap usage", 'sum(jvm_memory_used_bytes{application="student-management",area="heap"})', "bytes"),
    ("Process CPU", 'process_cpu_usage{application="student-management"}', "percentunit"),
]
panels = []
for index, (title, expression, unit) in enumerate(queries):
    panels.append({"id": index + 1, "title": title, "type": "timeseries",
                   "gridPos": {"x": (index % 2) * 12, "y": (index // 2) * 8, "w": 12, "h": 8},
                   "datasource": {"type": "prometheus", "uid": "prometheus"},
                   "targets": [{"refId": "A", "expr": expression}],
                   "fieldConfig": {"defaults": {"unit": unit}, "overrides": []}})
dashboard = {"uid": "student-devsecops", "title": "Student API - DevSecOps Lab", "schemaVersion": 41,
             "version": 1, "refresh": "15s", "time": {"from": "now-30m", "to": "now"}, "panels": panels}
output = 'apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: student-dashboard\n  namespace: student\ndata:\n  student.json: |\n'
output += "\n".join("    " + line for line in json.dumps(dashboard, indent=2).splitlines()) + "\n"
(Path(__file__).resolve().parents[1] / "monitoring" / "dashboard.yaml").write_text(output, encoding="utf-8")
