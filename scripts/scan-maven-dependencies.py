"""Scan the source POM before compilation and reject an empty dependency inventory."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def inventory(report):
    packages = [p for result in report.get("Results", []) if result.get("Type") == "pom"
                for p in result.get("Packages", [])]
    required = {"org.springframework:spring-webmvc", "org.apache.tomcat.embed:tomcat-embed-core",
                "com.mysql:mysql-connector-j", "org.springdoc:springdoc-openapi-starter-webmvc-ui"}
    missing = required - {p.get("Name") for p in packages}
    if not packages or missing:
        raise ValueError("Dependency inventory incomplete; missing expected runtime packages: " + ", ".join(sorted(missing)))
    if any(not p.get("Version") or not p.get("Identifier", {}).get("PURL", "").startswith("pkg:maven/") for p in packages):
        raise ValueError("Every analyzed dependency must have a version and Maven package URL")
    return packages


def main():
    output = Path(sys.argv[1] if len(sys.argv) > 1 else ".tools/reports/dependencies").resolve()
    output.mkdir(parents=True, exist_ok=True)
    scanner = ROOT / ".tools" / ("trivy.exe" if os.name == "nt" else "trivy")
    report = output / "dependencies.json"
    # Scan only this project's source manifest, without compiled output, another
    # project's POM or an unrelated cached JAR making an empty scan look useful.
    source = (ROOT / "pom.xml").read_bytes()
    (output / "pom.xml").write_bytes(source)
    with tempfile.TemporaryDirectory(prefix="course-pom-") as folder:
        (Path(folder) / "pom.xml").write_bytes(source)
        command = [str(scanner), "fs", "--scanners", "vuln", "--pkg-types", "library",
                                 "--list-all-pkgs", "--severity", "HIGH,CRITICAL", "--exit-code", "1",
                                 "--no-progress", "--format", "json", "--output", str(report)]
        if "--offline" in sys.argv[2:]:
            command.append("--offline-scan")
        result = subprocess.run(command + [folder])
    if result.returncode not in (0, 1) or not report.is_file():
        raise SystemExit("Trivy did not produce a valid dependency scan")
    data = json.loads(report.read_text(encoding="utf-8"))
    packages = inventory(data)
    subprocess.run([str(scanner), "convert", "--format", "cyclonedx", "--output",
                    str(output / "sbom.cdx.json"), str(report)], check=True)
    sbom = json.loads((output / "sbom.cdx.json").read_text(encoding="utf-8"))
    expected = {p["Identifier"]["PURL"] for p in packages}
    actual = {c.get("purl") for c in sbom.get("components", [])}
    if not expected.issubset(actual):
        raise SystemExit("Generated SBOM lost packages from the analyzed inventory")
    findings = [v for r in data.get("Results", []) for v in r.get("Vulnerabilities", [])]
    summary = {"source": "pom.xml before Maven compilation", "pom_sha256": hashlib.sha256(source).hexdigest(),
               "packages_analyzed": len(packages), "sbom_components": len(sbom.get("components", [])),
               "high_critical_findings": len(findings), "scanner_exit_code": result.returncode,
               "scope": "Trivy Maven compile/runtime/import scopes; test and optional dependencies excluded"}
    (output / "inventory-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
