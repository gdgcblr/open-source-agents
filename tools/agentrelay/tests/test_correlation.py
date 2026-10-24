"""Unit tests for cross-workflow correlation and non-causality guarantees."""

import unittest
from agentrelay.correlation import correlate_review_and_incident


class TestCorrelation(unittest.TestCase):
    """Test correlation matching, missing identifiers, conflict detection, and non-causality."""

    def test_exact_commit_match(self):
        review = {
            "execution_metadata": {"commit_id": "sha-abc-123", "service": "payment-api"},
            "findings": [{"claim": "SQL injection vulnerability in checkout", "severity": "high", "confidence": "medium", "evidence_ids": ["ev-1"]}],
        }
        incident = {
            "incident_id": "INC-100",
            "service": "payment-api",
            "deployments": [{"deployment_id": "dep-1", "commit_id": "sha-abc-123", "service": "payment-api"}],
            "logs": [{"id": "log-1", "level": "ERROR", "message": "Crash"}],
        }
        report = correlate_review_and_incident(review, incident)
        self.assertEqual(len(report.correlations), 1)
        link = report.correlations[0]
        self.assertEqual(link.relation_type, "exact_commit_match")
        self.assertFalse(link.is_causal_proof)
        self.assertIn("ASSOCIATION ONLY", link.caution_note)

    def test_conflicting_services_flagged(self):
        review = {
            "execution_metadata": {"commit_id": "sha-xyz", "service": "frontend-web"},
            "findings": [{"claim": "Unsafe eval in bundle", "severity": "high", "confidence": "medium", "evidence_ids": ["ev-2"]}],
        }
        incident = {
            "incident_id": "INC-200",
            "service": "database-cluster",
            "deployments": [{"deployment_id": "dep-2", "commit_id": "sha-xyz", "service": "database-cluster"}],
        }
        report = correlate_review_and_incident(review, incident)
        self.assertEqual(len(report.correlations), 1)
        link = report.correlations[0]
        self.assertEqual(link.relation_type, "conflicting_service_match")
        self.assertIn("CONFLICTING EVIDENCE", link.caution_note)

    def test_service_match_without_commit(self):
        review = {
            "execution_metadata": {"commit_id": "sha-1", "service": "search-svc"},
            "findings": [{"claim": "Memory leak", "severity": "low", "confidence": "low", "evidence_ids": ["ev-3"]}],
        }
        incident = {
            "incident_id": "INC-300",
            "service": "search-svc",
            "deployments": [{"deployment_id": "dep-3", "commit_id": "sha-2", "service": "search-svc"}],
        }
        report = correlate_review_and_incident(review, incident)
        self.assertEqual(len(report.correlations), 1)
        link = report.correlations[0]
        self.assertEqual(link.relation_type, "service_match_only")
        self.assertIn("WEAK ASSOCIATION", link.caution_note)

    def test_missing_identifiers_unlinked(self):
        review = {
            "execution_metadata": {},  # No commit, no service
            "findings": [{"claim": "Generic finding", "severity": "low", "confidence": "low", "evidence_ids": ["ev-4"]}],
        }
        incident = {
            "incident_id": "INC-400",
            "deployments": [],
        }
        report = correlate_review_and_incident(review, incident)
        self.assertEqual(len(report.correlations), 0)
        self.assertIn("Generic finding", report.unlinked_review_findings)


if __name__ == "__main__":
    unittest.main()
