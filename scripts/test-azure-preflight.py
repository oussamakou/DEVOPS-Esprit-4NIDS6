"""Exercise Azure's SKU restriction shapes without a subscription or resources."""
from pathlib import Path
import runpy
import unittest

validate = runpy.run_path(str(Path(__file__).with_name("check-azure-skus.py")))["validate_sku"]


class SkuEligibilityTests(unittest.TestCase):
    def test_available_size(self):
        sku = {"name": "Standard_D4s_v4", "restrictions": []}
        self.assertEqual(validate([sku], "Standard_D4s_v4", "francecentral"), sku)

    def test_subscription_location_rejection(self):
        sku = {"name": "Standard_D4s_v4", "restrictions": [{"type": "Location", "values": ["francecentral"], "reasonCode": "NotAvailableForSubscription"}]}
        with self.assertRaisesRegex(ValueError, "NotAvailableForSubscription"):
            validate([sku], "Standard_D4s_v4", "francecentral")

    def test_zone_only_restriction_allows_unzoned_vm(self):
        sku = {"name": "Standard_D4s_v4", "restrictions": [{"type": "Zone", "values": ["francecentral"], "restrictionInfo": {"zones": ["1"]}}]}
        self.assertEqual(validate([sku], "Standard_D4s_v4", "francecentral"), sku)

    def test_restriction_info_location_is_checked(self):
        sku = {"name": "Standard_D4s_v4", "restrictions": [{"type": "Location", "restrictionInfo": {"locations": ["francecentral"]}}]}
        with self.assertRaises(ValueError):
            validate([sku], "Standard_D4s_v4", "francecentral")

    def test_similar_size_is_not_an_exact_match(self):
        with self.assertRaises(ValueError):
            validate([{"name": "Standard_D4s_v4_Promo"}], "Standard_D4s_v4", "francecentral")


if __name__ == "__main__":
    unittest.main()
