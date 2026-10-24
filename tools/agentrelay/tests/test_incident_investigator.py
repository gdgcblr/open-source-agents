"""Unit tests for production incident investigation and telemetry analysis."""

import unittest
from agentrelay.incident_investigator import analyze_metric_series, run_incident_investigation


class TestIncidentInvestigator(unittest.TestCase):
    """Test telemetry analysis, metric surge detection, hypothesis ranking, and abstention."""

    def test_analyze_metric_series_surge(self):
        datapoints = [
            {"timestamp": "10:00", "value": 0.01},
            {"timestamp": "10:05", "value": 0.01},
            {"timestamp": "10:10", "value": 0.15},
            {"timestamp": "10:15", "value": 0.20},
        ]
        res = analyze_metric_series("error_rate", datapoints, service="api")
        self.assertIsNotNone(res)
        self.assertEqual(res["peak_value"], 0.20)
        self.assertEqual(res["peak_timestamp"], "10:15")

    def test_analyze_metric_series_flat(self):
        datapoints = [
            {"timestamp": "10:00", "value": 1.0},
            {"timestamp": "10:05", "value": 1.02},
            {"timestamp": "10:10", "value": 0.99},
            {"timestamp": "10:15", "value": 1.01},
        ]
        res = analyze_metric_series("latency", datapoints)
        self.assertIsNone(res)

    def test_run_incident_investigation_full(self):
        incident = {
            "incident_id": "INC-1234",
            "service": "cart-service",
            "deployments": [
                {
                    "deployment_id": "dep-55",
                    "commit_id": "f1e2d3",
                    "service": "cart-service",
                    "timestamp": "2026-10-24T10:00:00Z",
                }
            ],
            "metrics": [
                {
                    "name": "http_5xx_rate",
                    "service": "cart-service",
                    "datapoints": [
                        {"timestamp": "09:50", "value": 0.0},
                        {"timestamp": "09:55", "value": 0.0},
                        {"timestamp": "10:05", "value": 0.3},
                        {"timestamp": "10:10", "value": 0.4},
                    ],
                }
            ],
            "logs": [
                {
                    "id": "log-1",
                    "level": "ERROR",
                    "message": "ConnectionRefused: database unavailable",
                    "service": "cart-service",
                },
                {
                    "id": "log-2",
                    "level": "ERROR",
                    "message": "ConnectionRefused: database unavailable",
                    "service": "cart-service",
                },
            ],
            "traces": [
                {
                    "trace_id": "trc-1",
                    "error": True,
                    "duration_ms": 5000,
                    "error_message": "Timeout",
                }
            ],
        }
        report, ev_store = run_incident_investigation(incident)

        self.assertFalse(report.execution_metadata["abstained"])
        self.assertGreater(len(report.findings), 0)
        self.assertGreater(len(report.alternative_hypotheses), 0)

        # Verify hypothesis ranks
        ranks = [h.rank for h in report.alternative_hypotheses]
        self.assertEqual(ranks, sorted(ranks))

        # Verify citation validity
        for f in report.findings:
            valid, errs = ev_store.verify_citations(f.evidence_ids)
            self.assertTrue(valid, f"Citations invalid: {errs}")

    def test_run_incident_investigation_abstention_on_empty(self):
        incident = {
            "incident_id": "INC-EMPTY",
            "service": "unknown",
            "deployments": [],
            "metrics": [],
            "logs": [],
        }
        report, ev_store = run_incident_investigation(incident)
        self.assertTrue(report.execution_metadata["abstained"])
        self.assertEqual(len(report.findings), 0)
        self.assertEqual(len(report.alternative_hypotheses), 0)
        self.assertTrue(any("insufficient evidence" in report.summary.lower() for _ in [1]))


if __name__ == "__main__":
    unittest.main()
