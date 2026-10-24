"""End-to-end integration tests for BlastRadius."""

import unittest
from pathlib import Path
from blast_radius.agent import BlastRadiusAgent
from blast_radius.reporter import ImpactReporter

BASE_DIR = Path(__file__).resolve().parent.parent
FIXTURE_REPO = BASE_DIR / "fixtures" / "sample_repo"
DIFF_PAYMENT = (BASE_DIR / "fixtures" / "changes" / "payment_logic_update.diff").read_text(encoding="utf-8")
DIFF_ORDER = (BASE_DIR / "fixtures" / "changes" / "order_validation_bugfix.diff").read_text(encoding="utf-8")


class TestEndToEndBlastRadius(unittest.TestCase):

    def setUp(self):
        self.agent = BlastRadiusAgent(repo_path=str(FIXTURE_REPO))

    def test_payment_logic_update_impact(self):
        report = self.agent.analyze_diff(DIFF_PAYMENT)

        self.assertEqual(len(report.changed_methods), 1)
        self.assertEqual(report.changed_methods[0].method_name, "processPayment")

        # Discovers production caller in OrderService#createOrder
        caller_methods = {c.caller_method for c in report.callers}
        self.assertIn("createOrder", caller_methods)

        # Discovers test recommendation
        test_classes = {t.test_class for t in report.recommended_tests}
        self.assertIn("OrderServiceTest", test_classes)

        # Check Markdown rendering
        md = ImpactReporter.to_markdown(report)
        self.assertIn("BlastRadius: Change Impact Analysis Report", md)
        self.assertIn("processPayment", md)
        self.assertIn("Limitations & Analysis Boundaries", md)

    def test_order_validation_bugfix_impact(self):
        report = self.agent.analyze_diff(DIFF_ORDER)

        self.assertEqual(len(report.changed_methods), 1)
        self.assertEqual(report.changed_methods[0].method_name, "validateOrder")

        # Should identify both createOrder caller and OrderServiceTest test caller
        self.assertTrue(len(report.callers) >= 2)
        self.assertEqual(len(report.uncovered_methods), 0)

        # Recommended test includes testValidateOrderInvalid
        test_methods = {t.test_method for t in report.recommended_tests if t.test_method}
        self.assertIn("testValidateOrderInvalid", test_methods)

        md = ImpactReporter.to_markdown(report)
        self.assertIn("mvn test -Dtest=", md)

    def test_empty_diff_handling(self):
        empty_diff = ""
        report = self.agent.analyze_diff(empty_diff)

        self.assertEqual(len(report.changed_methods), 0)
        self.assertEqual(len(report.callers), 0)
        self.assertEqual(len(report.recommended_tests), 0)
        self.assertEqual(report.risk.tier, "LOW")


if __name__ == "__main__":
    unittest.main()

