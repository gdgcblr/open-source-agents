"""Unit tests for Multi-Service Orchestrator."""

import unittest
from pathlib import Path
from blast_radius.orchestrator import MultiServiceOrchestrator

BASE_DIR = Path(__file__).resolve().parent.parent
MICROSERVICES_DIR = BASE_DIR / "fixtures" / "microservices"
DIFF_FILE = (BASE_DIR / "fixtures" / "changes" / "payment_service_pr.diff").read_text(encoding="utf-8")


class TestMultiServiceOrchestrator(unittest.TestCase):

    def setUp(self):
        self.orchestrator = MultiServiceOrchestrator()
        self.orchestrator.discover_services(str(MICROSERVICES_DIR))

    def test_service_discovery(self):
        registered = set(self.orchestrator.services.keys())
        self.assertIn("payment-service", registered)
        self.assertIn("order-service", registered)
        self.assertIn("inventory-service", registered)

    def test_orchestrate_pr_impact(self):
        report = self.orchestrator.orchestrate_pr_impact(DIFF_FILE, "payment-service")

        self.assertEqual(report.target_service, "payment-service")
        self.assertEqual(report.overall_risk.tier, "HIGH")

        # payment-service is target
        payment_impact = report.service_impacts["payment-service"]
        self.assertTrue(payment_impact.is_target_service)
        self.assertTrue(payment_impact.is_impacted)

        # order-service is impacted downstream
        order_impact = report.service_impacts["order-service"]
        self.assertFalse(order_impact.is_target_service)
        self.assertTrue(order_impact.is_impacted)
        self.assertEqual(order_impact.risk_tier, "HIGH")
        self.assertTrue(len(order_impact.direct_callers) >= 1)

        # inventory-service is unaffected
        inventory_impact = report.service_impacts["inventory-service"]
        self.assertFalse(inventory_impact.is_impacted)
        self.assertEqual(inventory_impact.risk_tier, "NONE")

        # Markdown rendering check
        md = report.to_markdown()
        self.assertIn("Multi-Service BlastRadius", md)
        self.assertIn("order-service", md)
        self.assertIn("inventory-service", md)


if __name__ == "__main__":
    unittest.main()

