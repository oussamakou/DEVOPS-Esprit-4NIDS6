"""Check subscription SKU restrictions before preparing a Cloud Shell plan.

This checks listed eligibility, not live allocation capacity. Quota and the actual
Terraform plan must still be reviewed before applying.
"""
import json
from pathlib import Path
import subprocess
import sys


def validate_sku(skus, size, location):
    matches = [sku for sku in skus if sku.get("name", "").casefold() == size.casefold()]
    if len(matches) != 1:
        raise ValueError(f"{size} was not uniquely listed for {location}; choose another size or region")
    sku = matches[0]
    for restriction in sku.get("restrictions", []):
        if restriction.get("type", "").casefold() != "location":
            continue  # A zone-only restriction does not prohibit an unzoned VM.
        locations = restriction.get("values", []) + restriction.get("restrictionInfo", {}).get("locations", [])
        if not locations or location.casefold() in [value.casefold() for value in locations]:
            reason = restriction.get("reasonCode", "subscription restriction")
            raise ValueError(f"{size} is restricted in {location}: {reason}")
    return sku


def main():
    if len(sys.argv) < 3:
        raise SystemExit("Usage: python scripts/check-azure-skus.py LOCATION VM_SIZE [VM_SIZE ...]")
    location, *sizes = sys.argv[1:]
    reports = []
    for size in sizes:
        raw = subprocess.check_output(["az", "vm", "list-skus", "--location", location,
                                       "--resource-type", "virtualMachines", "--size", size,
                                       "--all", "--output", "json"], text=True)
        skus = json.loads(raw)
        # Preserve the returned restrictions even when validation fails.
        reports.extend(skus)
        output = Path(__file__).resolve().parents[1] / ".tools/azure-skus.json"
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(reports, indent=2), encoding="utf-8")
        try:
            sku = validate_sku(skus, size, location)
        except ValueError as error:
            raise SystemExit(str(error)) from error
        capabilities = {item["name"]: item["value"] for item in sku.get("capabilities", [])}
        print(f"Eligible SKU: {size}; family={sku.get('family')}; vCPUs={capabilities.get('vCPUs')}; memoryGB={capabilities.get('MemoryGB')}")
    print("SKU eligibility checked. Review remaining regional/family quota and the plan; live capacity is checked by Azure during deployment.")


if __name__ == "__main__":
    main()
