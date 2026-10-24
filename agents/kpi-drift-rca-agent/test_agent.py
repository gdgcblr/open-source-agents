"""
Test Suite for KPI Drift RCA Agent
===================================
Comprehensive automated test suite covering deterministic decomposition,
guardrails, stakeholder dispatch sub-agent, and synthetic data generation.

Run with:
  python test_agent.py
  # or
  python -m unittest test_agent.py -v
"""

import os
import tempfile
import unittest
import pandas as pd

from main import (
    compute_kpi_drift,
    validate_csv,
    format_ascii_waterfall,
    generate_synthetic_dataset,
    _sanitize_for_prompt,
    _sanitize_drivers,
    _MAX_CSV_SIZE_BYTES,
)
from stakeholder_dispatch import (
    dispatch_stakeholder_actions,
    format_dispatch_terminal,
    format_dispatch_markdown,
)


class TestKPIAgent(unittest.TestCase):
    def setUp(self):
        # Sample baseline and current data
        self.dimensions = ["country", "device", "channel"]
        self.df_base = pd.DataFrame([
            {"country": "IN", "device": "Mobile", "channel": "Organic", "conversions": 450, "sessions": 9000},
            {"country": "IN", "device": "Desktop", "channel": "Organic", "conversions": 300, "sessions": 5000},
            {"country": "US", "device": "Mobile", "channel": "Paid", "conversions": 600, "sessions": 10000},
            {"country": "US", "device": "Desktop", "channel": "Paid", "conversions": 500, "sessions": 6000},
            {"country": "UK", "device": "Mobile", "channel": "Direct", "conversions": 200, "sessions": 4000},
            {"country": "UK", "device": "Desktop", "channel": "Direct", "conversions": 150, "sessions": 2500},
        ])
        self.df_curr = pd.DataFrame([
            {"country": "IN", "device": "Mobile", "channel": "Organic", "conversions": 460, "sessions": 9100},
            {"country": "IN", "device": "Desktop", "channel": "Organic", "conversions": 290, "sessions": 4900},
            {"country": "US", "device": "Mobile", "channel": "Paid", "conversions": 180, "sessions": 9800},
            {"country": "US", "device": "Desktop", "channel": "Paid", "conversions": 480, "sessions": 5900},
            {"country": "UK", "device": "Mobile", "channel": "Direct", "conversions": 195, "sessions": 3950},
            {"country": "UK", "device": "Desktop", "channel": "Direct", "conversions": 145, "sessions": 2450},
        ])

    # -------------------------------------------------------------------------
    # 1. Deterministic Decomposition Tests
    # -------------------------------------------------------------------------
    def test_volume_drift_math(self):
        """Verify 100% exact math calculation for totals and deltas without hallucinations."""
        stats = compute_kpi_drift(self.df_base, self.df_curr, self.dimensions, "conversions", "sessions")
        self.assertEqual(stats["baseline_total"], 2200.0)
        self.assertEqual(stats["current_total"], 1750.0)
        self.assertEqual(stats["absolute_delta"], -450.0)
        self.assertAlmostEqual(stats["percentage_change"], -20.45, places=2)

        # Culprit cohort must be US / Mobile / Paid with -420 delta
        top_drag = stats["primary_negative_drivers"][0]
        self.assertEqual(top_drag["country"], "US")
        self.assertEqual(top_drag["device"], "Mobile")
        self.assertEqual(top_drag["channel"], "Paid")
        self.assertEqual(top_drag["delta"], -420.0)
        self.assertAlmostEqual(top_drag["pct_contribution"], -93.33, places=2)

    def test_rate_decomposition(self):
        """Verify dual-metric conversion rate decomposition."""
        stats = compute_kpi_drift(self.df_base, self.df_curr, self.dimensions, "conversions", "sessions")
        self.assertIsNotNone(stats["rate_decomposition"])
        worst_rate = stats["rate_decomposition"][0]
        self.assertEqual(worst_rate["country"], "US")
        self.assertEqual(worst_rate["device"], "Mobile")
        self.assertEqual(worst_rate["channel"], "Paid")
        self.assertEqual(worst_rate["rate_baseline"], 6.0)
        self.assertAlmostEqual(worst_rate["rate_current"], 1.8367, places=4)
        self.assertAlmostEqual(worst_rate["rate_delta_pp"], -4.1633, places=4)

    def test_optional_rate_decomposition_disabled(self):
        """Verify rate decomposition is gracefully omitted when secondary metric is None."""
        stats = compute_kpi_drift(self.df_base, self.df_curr, self.dimensions, "conversions", None)
        self.assertIsNone(stats["rate_decomposition"])

    # -------------------------------------------------------------------------
    # 2. Guardrails Tests
    # -------------------------------------------------------------------------
    def test_prompt_injection_sanitization(self):
        """Verify dimension values are sanitized against prompt injection patterns."""
        malicious_input = "US'; DROP TABLE users; -- <script>alert(1)</script>"
        sanitized = _sanitize_for_prompt(malicious_input)
        self.assertNotIn(";", sanitized)
        self.assertNotIn("<", sanitized)
        self.assertNotIn(">", sanitized)
        self.assertNotIn("'", sanitized)

        # Test driver dictionary sanitization
        drivers = [{"country": malicious_input, "delta": -100}]
        clean_drivers = _sanitize_drivers(drivers, ["country"])
        self.assertNotIn(";", clean_drivers[0]["country"])

    def test_csv_validation_missing_columns(self):
        """Verify schema validation rejects CSV when required columns are absent."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("country,device,sessions\nUS,Mobile,1000\n")
            temp_path = f.name

        try:
            with self.assertRaises(SystemExit) as cm:
                validate_csv(temp_path, ["country", "device", "conversions"], "Test")
            self.assertEqual(cm.exception.code, 1)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_csv_validation_oversized_file(self):
        """Verify file-size guardrail rejects files exceeding size limit."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("a,b\n1,2\n")
            temp_path = f.name

        # Mock os.path.getsize to simulate file > 10MB
        real_getsize = os.path.getsize
        try:
            os.path.getsize = lambda p: _MAX_CSV_SIZE_BYTES + 1024
            with self.assertRaises(SystemExit) as cm:
                validate_csv(temp_path, ["a", "b"], "Test")
            self.assertEqual(cm.exception.code, 1)
        finally:
            os.path.getsize = real_getsize
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # -------------------------------------------------------------------------
    # 3. Stakeholder Dispatch Sub-Agent Tests
    # -------------------------------------------------------------------------
    def test_stakeholder_dispatch_offline_mode(self):
        """Verify Stakeholder Dispatch Sub-Agent generates 3 assigned tickets with SLAs."""
        stats = compute_kpi_drift(self.df_base, self.df_curr, self.dimensions, "conversions", "sessions")
        dispatch = dispatch_stakeholder_actions(stats, "Sample diagnosis text", self.dimensions, client=None)

        self.assertIn("incident_severity", dispatch)
        self.assertIn("actions", dispatch)
        self.assertEqual(len(dispatch["actions"]), 3)

        roles = [a["assignee_role"] for a in dispatch["actions"]]
        self.assertIn("Engineering / DevOps Lead", roles)
        self.assertIn("Growth / Paid Media Lead", roles)
        self.assertIn("Regional / Geography Manager", roles)

        # Each action must have required fields
        for action in dispatch["actions"]:
            self.assertIn(action["priority"], ["P0", "P1", "P2"])
            self.assertTrue(len(action["sla"]) > 0)
            self.assertTrue(len(action["investigation_focus"]) > 0)
            self.assertTrue(len(action["expected_resolution"]) > 0)

    def test_dispatch_formatting(self):
        """Verify terminal and markdown formatters for dispatch matrix produce non-empty strings."""
        stats = compute_kpi_drift(self.df_base, self.df_curr, self.dimensions, "conversions", "sessions")
        dispatch = dispatch_stakeholder_actions(stats, "Sample diagnosis text", self.dimensions, client=None)

        terminal_str = format_dispatch_terminal(dispatch)
        self.assertIn("MULTI-AGENT STAKEHOLDER INCIDENT ACTION DISPATCH MATRIX", terminal_str)
        self.assertIn("Engineering / DevOps Lead", terminal_str)

        markdown_str = format_dispatch_markdown(dispatch)
        self.assertIn("## Multi-Agent Stakeholder Incident Dispatch", markdown_str)
        self.assertIn("| Priority | Assignee Role | SLA |", markdown_str)

    # -------------------------------------------------------------------------
    # 4. Synthetic Sample Generator Tests
    # -------------------------------------------------------------------------
    def test_synthetic_data_scenarios(self):
        """Verify all synthetic scenarios generate valid baseline and current DataFrames."""
        scenarios = [
            "checkout_dropoff",
            "payment_gateway_failure",
            "mobile_release_regression",
            "ad_campaign_fatigue",
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            base_p = os.path.join(tmpdir, "base.csv")
            curr_p = os.path.join(tmpdir, "curr.csv")

            for sc in scenarios:
                df_b, df_c = generate_synthetic_dataset(sc, base_p, curr_p)
                self.assertGreater(len(df_b), 0)
                self.assertGreater(len(df_c), 0)
                for req in ["country", "device", "channel", "conversions", "sessions"]:
                    self.assertIn(req, df_b.columns)
                    self.assertIn(req, df_c.columns)

    # -------------------------------------------------------------------------
    # 5. ASCII Waterfall & Visualization Tests
    # -------------------------------------------------------------------------
    def test_ascii_waterfall_output(self):
        """Verify ASCII waterfall chart renders correctly and contains key components."""
        stats = compute_kpi_drift(self.df_base, self.df_curr, self.dimensions, "conversions", "sessions")
        waterfall = format_ascii_waterfall(stats, self.dimensions)
        self.assertIn("METRIC DRIFT WATERFALL SUMMARY", waterfall)
        self.assertIn("Baseline Total", waterfall)
        self.assertIn("Current Total", waterfall)
        self.assertIn("US / Mobile / Paid", waterfall)


if __name__ == "__main__":
    unittest.main(verbosity=2)
