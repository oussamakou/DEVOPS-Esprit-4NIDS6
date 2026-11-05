"""Verify that Nexus stores exactly the JAR that passed the Maven tests.

Maven's -ntp flag hides upload lines, so the log alone cannot show what Nexus
holds. This reads the repository's own maven-metadata.xml, finds the newest
snapshot JAR, downloads its published SHA-1 and compares it with the local JAR.

Usage (CI): NEXUS_USERNAME / NEXUS_PASSWORD in the environment, then
  python scripts/nexus-artifact-report.py NEXUS_MAVEN_URL JAR POM REPORT_DIR
The password is only sent as a Basic-auth header and is never printed.
"""
import base64
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

POM_NS = {"m": "http://maven.apache.org/POM/4.0.0"}


def safe_xml(data):
    """Parse XML only if it declares no DTD or entities (blocks entity expansion)."""
    text = data if isinstance(data, bytes) else data.encode()
    if b"<!DOCTYPE" in text.upper() or b"<!ENTITY" in text.upper():
        raise ValueError("XML with a DTD or entity declaration is rejected")
    return ET.fromstring(text)


def coordinates(pom_path):
    root = safe_xml(Path(pom_path).read_bytes())

    def field(name):
        element = root.find(f"m:{name}", POM_NS)
        if element is None or not (element.text or "").strip():
            raise ValueError(f"pom.xml has no project-level <{name}>")
        return element.text.strip()
    return field("groupId"), field("artifactId"), field("version")


def fetch(url, username, password, timeout=30):
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    request = urllib.request.Request(url, headers={"Authorization": f"Basic {token}",
                                                   "User-Agent": "student-devsecops-lab"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def newest_jar_value(metadata_xml):
    """Return (snapshot version string, lastUpdated) for the newest jar."""
    root = safe_xml(metadata_xml)
    versioning = root.find("versioning")
    if versioning is None:
        raise ValueError("maven-metadata.xml has no <versioning> section")
    last_updated = (versioning.findtext("lastUpdated") or "").strip()
    jars = [(entry.findtext("updated") or "", entry.findtext("value") or "")
            for entry in versioning.findall("snapshotVersions/snapshotVersion")
            if (entry.findtext("extension") or "") == "jar" and not entry.findtext("classifier")]
    if jars:
        return max(jars)[1], last_updated
    snapshot = versioning.find("snapshot")
    if snapshot is not None and snapshot.findtext("timestamp") and snapshot.findtext("buildNumber"):
        return None, last_updated  # caller composes version from the snapshot block
    raise ValueError("maven-metadata.xml lists no jar snapshot")


def verify(base_url, jar_path, pom_path, username, password, attempts=3, delay=3, require_https=True):
    if require_https and not base_url.startswith("https://"):
        raise ValueError("NEXUS_MAVEN_URL must be HTTPS")
    base = base_url.rstrip("/") + "/"
    group, artifact, version = coordinates(pom_path)
    directory = f"{base}{group.replace('.', '/')}/{artifact}/{version}/"
    jar = Path(jar_path).read_bytes()
    local_sha1 = hashlib.sha1(jar).hexdigest()  # noqa: S324 - Maven publishes SHA-1 checksums
    last_error = None
    for attempt in range(attempts):
        try:
            metadata = fetch(directory + "maven-metadata.xml", username, password)
            value, last_updated = newest_jar_value(metadata)
            if value is None:
                snap = safe_xml(metadata).find("versioning/snapshot")
                value = f"{version.replace('-SNAPSHOT', '')}-{snap.findtext('timestamp')}-{snap.findtext('buildNumber')}"
            jar_url = f"{directory}{artifact}-{value}.jar"
            remote_sha1 = fetch(jar_url + ".sha1", username, password).decode().split()[0].lower()
            return {"repository_url": directory, "stored_jar": jar_url, "snapshot_version": value,
                    "last_updated": last_updated, "local_sha1": local_sha1, "remote_sha1": remote_sha1,
                    "size_bytes": str(len(jar)), "match": str(remote_sha1 == local_sha1).lower()}
        except (urllib.error.URLError, ValueError, ET.ParseError, IndexError) as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(delay)
    raise RuntimeError(f"Nexus verification failed after {attempts} attempts: {type(last_error).__name__}: {last_error}")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit(__doc__)
    url, jar, pom, report_dir = sys.argv[1:]
    if not os.environ.get("NEXUS_USERNAME") or not os.environ.get("NEXUS_PASSWORD"):
        raise SystemExit("NEXUS_USERNAME and NEXUS_PASSWORD are required")
    result = verify(url, jar, pom, os.environ["NEXUS_USERNAME"], os.environ["NEXUS_PASSWORD"])
    spec = importlib.util.spec_from_file_location("stage_facts", Path(__file__).with_name("stage-facts.py"))
    stage_facts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stage_facts)
    stage_facts.record(report_dir, "nexus-artifact", [f"{k}={v}" for k, v in result.items()])
    for key, value in result.items():
        print(f"{key}: {value}")
    if result["match"] != "true":
        raise SystemExit("Nexus stores a JAR whose SHA-1 differs from the tested JAR")
    print("NEXUS_VERIFIED: stored JAR matches the tested JAR")
