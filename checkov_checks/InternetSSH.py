"""Close the scanner's literal-CIDR blind spot as well as blocking wildcard SSH."""
import ipaddress

from checkov.common.models.enums import CheckCategories, CheckResult
from checkov.terraform.checks.resource.base_resource_check import BaseResourceCheck


class InternetSSH(BaseResourceCheck):
    def __init__(self):
        super().__init__(name="Block internet-wide inbound SSH including literal /0 CIDRs",
                         id="CKV_LAB_1", categories=[CheckCategories.NETWORKING],
                         supported_resources=["azurerm_network_security_rule", "azurerm_network_security_group"])

    def scan_resource_conf(self, conf):
        for rule in conf.get("security_rule", [conf]):
            if not isinstance(rule, dict):
                continue
            get = lambda key, default="": rule.get(key, [default])[0]
            if str(get("access")).lower() != "allow" or str(get("direction")).lower() != "inbound":
                continue
            if str(get("protocol")).lower() not in ("tcp", "*"):
                continue
            ports = get("destination_port_ranges", None) or [get("destination_port_range")]
            includes_ssh = False
            for value in ports:
                value = str(value)
                if value in ("*", "22"):
                    includes_ssh = True
                elif "-" in value:
                    bounds = value.split("-")
                    if len(bounds) == 2 and all(b.isdecimal() for b in bounds):
                        includes_ssh |= int(bounds[0]) <= 22 <= int(bounds[1])
            if not includes_ssh:
                continue
            sources = get("source_address_prefixes", None) or [get("source_address_prefix")]
            for source in sources:
                if str(source).lower() in ("*", "any", "internet", "0.0.0.0", "<nw>/0", "/0"):
                    return CheckResult.FAILED
                try:
                    if ipaddress.ip_network(source, strict=False).prefixlen == 0:
                        return CheckResult.FAILED
                except ValueError:
                    pass  # Terraform separately validates the owner admin_cidr as an IPv4 /32.
        return CheckResult.PASSED


check = InternetSSH()
