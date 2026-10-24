"""Unit tests for AgentRelay schemas and validation."""

import unittest
from agentrelay.schemas import (
    EvidenceRecord,
    Finding,
    Hypothesis,
    InvestigationReport,
    CorrelationLink,
    CorrelationReport,
    ValidationError,
)


class TestSchemas(unittest.TestCase):
    """Test schema instantiation, serialization, and validation rules."""

    def test_evidence_record_valid(self):
        ev = EvidenceRecord(
            id="ev-01",
            source_type="diff",
            content="Line added: query = f'SELECT...'",
            service="auth-service",
            commit_id="sha-123",
            deployment_id="dep-456",
            metadata={"line": 42},
        )
        self.assertEqual(ev.validate(), [])
        d = ev.to_dict()
        self.assertEqual(d["id"], "ev-01")
        self.assertEqual(d["source_type"], "diff")

        reconstructed = EvidenceRecord.from_dict(d)
        self.assertEqual(reconstructed.id, "ev-01")

    def test_evidence_record_invalid_source_type(self):
        ev = EvidenceRecord(id="ev-02", source_type="invalid_type", content="test")
        errors = ev.validate()
        self.assertTrue(any("Invalid source_type" in err for err in errors))

    def test_finding_validation_and_citation_check(self):
        finding = Finding(
            claim="SQL injection in auth",
            severity="high",
            confidence="medium",
            evidence_ids=["ev-01"],
            explanation="Unparameterized query detected.",
            recommended_next_action="Use parameterized query.",
        )
        # Valid when citing known ID
        self.assertEqual(finding.validate(known_evidence_ids={"ev-01"}), [])

        # Fails when citing unknown ID
        errors = finding.validate(known_evidence_ids={"ev-different"})
        self.assertTrue(any("nonexistent evidence" in err for err in errors))

    def test_finding_high_confidence_requires_two_citations(self):
        # High confidence with only 1 citation must fail
        finding = Finding(
            claim="Critical flaw",
            severity="critical",
            confidence="high",
            evidence_ids=["ev-01"],
            explanation="Test",
            recommended_next_action="Fix",
        )
        errors = finding.validate(known_evidence_ids={"ev-01", "ev-02"})
        self.assertTrue(any("requires at least 2 distinct" in err for err in errors))

        # High confidence with 2 distinct citations must pass
        finding.evidence_ids = ["ev-01", "ev-02"]
        self.assertEqual(finding.validate(known_evidence_ids={"ev-01", "ev-02"}), [])

    def test_hypothesis_validation(self):
        hypo = Hypothesis(
            title="Database lock contention",
            rank=1,
            likelihood="plausible",
            supporting_evidence_ids=["ev-log-1"],
            contradicting_evidence_ids=[],
            missing_telemetry=["lock metrics"],
            explanation="Logs show deadlock.",
        )
        self.assertEqual(hypo.validate(known_evidence_ids={"ev-log-1"}), [])

        # Fails if referencing non-existent evidence
        errors = hypo.validate(known_evidence_ids={"other-id"})
        self.assertTrue(any("nonexistent supporting evidence" in err for err in errors))

    def test_investigation_report_roundtrip(self):
        ev_id = "ev-test-1"
        finding = Finding(
            claim="Memory leak risk",
            severity="medium",
            confidence="low",
            evidence_ids=[ev_id],
            explanation="Resource unclosed.",
            recommended_next_action="Close file descriptor.",
        )
        report = InvestigationReport(
            summary="Review finished with 1 finding.",
            findings=[finding],
            unknowns=["Production load unknown."],
            recommendations=["Add tests."],
            execution_metadata={"env": "test"},
        )
        self.assertEqual(report.validate(known_evidence_ids={ev_id}), [])

        d = report.to_dict()
        reconstructed = InvestigationReport.from_dict(d, known_evidence_ids={ev_id})
        self.assertEqual(reconstructed.summary, report.summary)
        self.assertEqual(len(reconstructed.findings), 1)

    def test_correlation_never_claims_causation(self):
        link = CorrelationLink(
            relation_type="exact_commit_match",
            basis="Commit sha matched deployment.",
            review_claim="SQL flaw",
            incident_event_id="INC-1",
            is_causal_proof=False,
        )
        self.assertFalse(link.is_causal_proof)
        self.assertIn("ASSOCIATION ONLY", link.caution_note)


if __name__ == "__main__":
    unittest.main()
