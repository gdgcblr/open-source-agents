"""Exercise the optional transport without sending test data over the network."""

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from first_run_doctor.diagnose import jev_diagnosis


@unittest.skipUnless(
    importlib.util.find_spec("requests") and importlib.util.find_spec("dotenv"),
    "Optional [jev] extra not installed",
)
class JevTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = Path(self.temp.name) / ".env"
        self.key = "test-only-jev-key-not-a-real-credential"
        self.env.write_text("EXPERIENTIAL_API_KEY=" + self.key + "\n")
        self.report = {
            "verification": "failed",
            "checks": [{"id": "A1", "status": "fail", "detail": "Missing artifact"}],
            "execution": {"status": "completed", "returncode": 0, "stderr": self.key},
        }
        self.answer = {
            "answers": {
                "cause": {"type": "choice", "choice": "output_contract_failure", "confidence": 0.8}
            }
        }

    def request(self, answer=None, error=None):
        session = MagicMock()
        response = MagicMock()
        response.status_code = 200
        response.__enter__.return_value = response
        response.iter_content.return_value = [json.dumps(answer or self.answer).encode()]
        session.post.return_value = response
        if error:
            session.post.side_effect = error
        with patch("requests.Session") as factory:
            factory.return_value.__enter__.return_value = session
            result = jev_diagnosis(self.report, self.env)
        return result, session

    def test_valid_answer_is_advisory_and_payload_is_redacted(self):
        result, session = self.request()
        self.assertEqual(result["category"], "output_contract_failure")
        self.assertTrue(result["advisory"])
        call = session.post.call_args
        self.assertNotIn(self.key, json.dumps(call.kwargs["json"]))
        self.assertEqual(call.kwargs["timeout"], (10, 60))
        self.assertFalse(call.kwargs["allow_redirects"])
        self.assertFalse(session.trust_env)
        session.post.assert_called_once()

    def test_timeout_does_not_retry_or_expose_exception_details(self):
        import requests

        result, session = self.request(error=requests.Timeout(self.key))
        self.assertEqual(result["source"], "unavailable")
        self.assertNotIn(self.key, json.dumps(result))
        session.post.assert_called_once()

    def test_unsupported_and_invalid_typed_answers_are_unavailable(self):
        for field, value in (
            ("choice", "execute_shell"),
            ("confidence", True),
            ("confidence", 2),
            ("type", "score"),
        ):
            answer = copy.deepcopy(self.answer)
            answer["answers"]["cause"][field] = value
            result, _ = self.request(answer)
            self.assertEqual(result["source"], "unavailable")

    def test_large_evidence_is_bounded_and_failures_are_prioritized(self):
        self.report["checks"] = [
            {"id": str(i), "status": "pass", "detail": "x" * 3000} for i in range(100)
        ] + [{"id": "FAIL", "status": "fail", "detail": "missing"}]
        _, session = self.request()
        evidence = session.post.call_args.kwargs["json"]["state"]["checks"]
        self.assertLessEqual(len(evidence), 24)
        self.assertEqual(evidence[0]["id"], "FAIL")


if __name__ == "__main__":
    unittest.main()
