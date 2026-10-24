"""Unit tests for OSS Project Scout Guardrails and Ranking."""

import unittest
from guardrails import RepoGuardrail, GuardrailViolationError
from github_client import GitHubScoutClient


class TestGuardrails(unittest.TestCase):
    def setUp(self):
        self.verified_sample = [
            {
                "rank": 1,
                "name": "fastapi",
                "full_name": "tiangolo/fastapi",
                "html_url": "https://github.com/tiangolo/fastapi",
                "stars": 75000,
                "forks": 6000,
                "open_issues_count": 200,
            },
            {
                "rank": 2,
                "name": "flask",
                "full_name": "pallets/flask",
                "html_url": "https://github.com/pallets/flask",
                "stars": 67000,
                "forks": 15000,
                "open_issues_count": 10,
            }
        ]
        self.guardrail = RepoGuardrail(self.verified_sample)

    def test_verified_repo_passes(self):
        llm_output = [
            {
                "full_name": "tiangolo/fastapi",
                "html_url": "https://github.com/tiangolo/fastapi",
                "problem_statement": "High-performance web framework for APIs.",
            }
        ]
        verified, violations = self.guardrail.validate_and_filter_summaries(llm_output, strict=True)
        self.assertEqual(len(verified), 1)
        self.assertEqual(len(violations), 0)
        self.assertEqual(verified[0]["guardrail_status"], "VERIFIED_GENUINE")

    def test_hallucinated_repo_blocked_in_strict_mode(self):
        hallucinated_output = [
            {
                "full_name": "fake-author/fake-nonexistent-repo",
                "html_url": "https://github.com/fake-author/fake-nonexistent-repo",
                "problem_statement": "Hallucinated repo that does not exist in Step 1.",
            }
        ]
        with self.assertRaises(GuardrailViolationError):
            self.guardrail.validate_and_filter_summaries(hallucinated_output, strict=True)

    def test_hallucinated_repo_stripped_in_lenient_mode(self):
        mixed_output = [
            {
                "full_name": "pallets/flask",
                "html_url": "https://github.com/pallets/flask",
                "problem_statement": "Micro web framework.",
            },
            {
                "full_name": "random/hallucinated-tool",
                "html_url": "https://github.com/random/hallucinated-tool",
                "problem_statement": "Fake item.",
            }
        ]
        verified, violations = self.guardrail.validate_and_filter_summaries(mixed_output, strict=False)
        self.assertEqual(len(verified), 1)
        self.assertEqual(len(violations), 1)
        self.assertEqual(verified[0]["full_name"], "pallets/flask")
        self.assertIn("random/hallucinated-tool", violations[0]["reason"])


if __name__ == "__main__":
    unittest.main()
