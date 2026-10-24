"""Unit tests proving model policy enforcement and deterministic priority."""

import unittest
from agentrelay.config import Config
from agentrelay.evidence import EvidenceStore
from agentrelay.model_client import MockModelClient, OfflineModelClient
from agentrelay.model_policy import (
    DETERMINISTIC_ONLY_TASKS,
    ModelPolicy,
)
from agentrelay.schemas import Finding, InvestigationReport


class TestModelPolicy(unittest.TestCase):
    """Test token efficiency, model invocation gating, and offline fallback."""

    def test_deterministic_tasks_never_call_model(self):
        """Prove that deterministic tasks NEVER trigger a model call under any configuration."""
        # Even with offline_mode=False and online provider set
        online_config = Config(offline_mode=False, model_provider="gemini", gemini_api_key="fake-key")
        policy = ModelPolicy(config=online_config, client=MockModelClient())

        for task in DETERMINISTIC_ONLY_TASKS:
            self.assertFalse(
                policy.should_invoke_model(task_name=task, force_semantic=True),
                f"Deterministic task '{task}' must never invoke model!",
            )

    def test_offline_mode_disables_all_model_calls(self):
        """Prove that offline mode guarantees zero model calls even for semantic tasks."""
        offline_config = Config(offline_mode=True, model_provider="offline")
        policy = ModelPolicy(config=offline_config, client=OfflineModelClient())

        self.assertFalse(
            policy.should_invoke_model(task_name="semantic_code_reasoning", force_semantic=True)
        )
        self.assertFalse(
            policy.should_invoke_model(task_name="incident_summary_synthesis", is_ambiguous=True)
        )

    def test_semantic_task_invokes_model_when_configured(self):
        """Prove that semantic tasks invoke model when enabled and configured."""
        online_config = Config(offline_mode=False, model_provider="mock")
        mock_client = MockModelClient(
            canned_json={
                "semantic_findings": [
                    {
                        "claim": "Complex race condition between thread A and thread B",
                        "severity": "high",
                        "confidence": "low",
                        "evidence_ids": ["ev-diff-1"],
                        "explanation": "Concurrent access without mutex lock.",
                        "recommended_next_action": "Acquire thread lock.",
                    }
                ]
            }
        )
        policy = ModelPolicy(config=online_config, client=mock_client)

        ev_store = EvidenceStore()
        from agentrelay.schemas import EvidenceRecord
        ev_store.add(EvidenceRecord(id="ev-diff-1", source_type="diff", content="code snippet"))

        deterministic_report = InvestigationReport(
            summary="Deterministic summary.",
            findings=[],
            unknowns=[],
            recommendations=[],
            execution_metadata={},
        )

        final_report = policy.run_semantic_code_review(
            diff_snippet="diff text",
            deterministic_report=deterministic_report,
            evidence_store=ev_store,
        )

        self.assertTrue(final_report.execution_metadata.get("model_invoked"))
        self.assertEqual(len(mock_client.call_history), 1)
        self.assertEqual(len(final_report.findings), 1)
        self.assertIn("Complex race condition", final_report.findings[0].claim)

    def test_semantic_task_rejects_hallucinated_evidence_ids(self):
        """Prove that model responses with fabricated evidence citations are discarded."""
        online_config = Config(offline_mode=False, model_provider="mock")
        mock_client = MockModelClient(
            canned_json={
                "semantic_findings": [
                    {
                        "claim": "Hallucinated claim",
                        "severity": "critical",
                        "confidence": "high",
                        "evidence_ids": ["ev-invented-ghost-99"],
                        "explanation": "Invented finding.",
                        "recommended_next_action": "Ignore.",
                    }
                ]
            }
        )
        policy = ModelPolicy(config=online_config, client=mock_client)

        ev_store = EvidenceStore()
        # Only ev-real exists in store
        from agentrelay.schemas import EvidenceRecord
        ev_store.add(EvidenceRecord(id="ev-real", source_type="diff", content="code snippet"))

        report = InvestigationReport(
            summary="Clean baseline.",
            findings=[],
            unknowns=[],
            recommendations=[],
            execution_metadata={},
        )

        final_report = policy.run_semantic_code_review(
            diff_snippet="diff text",
            deterministic_report=report,
            evidence_store=ev_store,
        )

        # The hallucinated finding citing ev-invented-ghost-99 must be rejected!
        self.assertEqual(len(final_report.findings), 0)


if __name__ == "__main__":
    unittest.main()
