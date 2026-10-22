"""Exercise Azure's SKU restriction shapes without a subscription or resources."""
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch
import subprocess
from contextlib import redirect_stdout
import io

helpers = runpy.run_path(str(Path(__file__).with_name("check-azure-skus.py")))
validate = helpers["validate_sku"]
fetch = helpers["fetch_skus"]
main = helpers["main"]


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

    def test_both_sizes_share_one_bounded_request(self):
        with patch("subprocess.check_output", return_value="[]") as query:
            self.assertEqual(fetch("francecentral", ["Standard_B2s", "Standard_D4s_v4"]), [])
        query.assert_called_once()
        self.assertEqual(query.call_args.kwargs["timeout"], 180)

    def test_slow_query_reports_an_actionable_failure(self):
        with patch("subprocess.check_output", side_effect=subprocess.TimeoutExpired("az", 180)):
            with self.assertRaisesRegex(ValueError, "timed out after 180 seconds"):
                fetch("francecentral", ["Standard_B2s"])

    def test_preparation_reports_every_requested_size_and_still_blocks(self):
        skus = [{"name": "Standard_B2s", "restrictions": [{"type": "Location", "values": ["francecentral"]}]},
                {"name": "Standard_D4s_v4", "restrictions": []}]
        output = io.StringIO()
        with patch.dict(main.__globals__, {"fetch_skus": lambda *_: skus}), \
                patch("sys.argv", ["check", "francecentral", "Standard_B2s", "Standard_D4s_v4"]), \
                patch.object(Path, "write_text"), redirect_stdout(output):
            with self.assertRaisesRegex(SystemExit, "Preparation blocked"):
                main()
        self.assertIn("RESTRICTED / UNLISTED", output.getvalue())
        self.assertIn("Eligible SKU: Standard_D4s_v4", output.getvalue())

    def test_report_only_lists_restrictions_without_starting_preparation(self):
        sku = {"name": "Standard_B2s", "restrictions": [{"type": "Location", "values": ["francecentral"]}]}
        output = io.StringIO()
        with patch.dict(main.__globals__, {"fetch_skus": lambda *_: [sku]}), \
                patch("sys.argv", ["check", "--report-only", "francecentral", "Standard_B2s"]), \
                patch.object(Path, "write_text"), redirect_stdout(output):
            main()
        self.assertIn("0 eligible, 1 restricted/unlisted", output.getvalue())


if __name__ == "__main__":
    unittest.main()
