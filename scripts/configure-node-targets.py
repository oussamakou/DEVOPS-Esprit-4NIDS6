"""Write persistent Prometheus file discovery on the application VM (run as root)."""
import argparse
import ipaddress
import json
import os
from pathlib import Path


def private_address(value, subnet):
    address = ipaddress.IPv4Address(value)
    if address not in ipaddress.IPv4Network(subnet):
        raise ValueError(f"Expected an address in {subnet}")
    return str(address)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app_private_ip")
    parser.add_argument("tools_private_ip")
    args = parser.parse_args()
    app = private_address(args.app_private_ip, "10.42.1.0/24")
    tools = private_address(args.tools_private_ip, "10.42.2.0/24")
    if os.geteuid() != 0:
        parser.error("Run with sudo on the application VM")
    targets = [
        {"targets": [f"{app}:9100"], "labels": {"host": "application-vm", "role": "application"}},
        {"targets": [f"{tools}:9100"], "labels": {"host": "tools-vm", "role": "sonarqube-nexus"}},
    ]
    directory = Path("/opt/student-course/node-targets")
    directory.mkdir(mode=0o755, parents=True, exist_ok=True)
    temporary = directory / "azure-vms.json.tmp"
    temporary.write_text(json.dumps(targets, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o644)
    temporary.replace(directory / "azure-vms.json")
    print("Node discovery updated for application-vm and tools-vm (private addresses only).")


if __name__ == "__main__":
    main()
