import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from securevantara.local_llm import review, validate


class LocalReviewTests(unittest.TestCase):
    def item(self):
        return dict(path="sample.py", line=1, title="Dynamic execution",
                    evidence="eval(x)", severity="high")

    def test_valid_evidence_is_unverified(self):
        result = validate({"findings": [self.item()]}, {"sample.py": "eval(x)"}, "test")
        self.assertEqual(result[0]["status"], "unverified")
        self.assertEqual(result[0]["provenance"][0]["model"], "test")

    def test_invalid_location_and_fields(self):
        for changes in [{"path": "../secret.py"}, {"line": 2}, {"line": True},
                        {"evidence": "invented"}, {"severity": "confirmed"}, {"title": ""}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate({"findings": [dict(self.item(), **changes)]}, {"sample.py": "eval(x)"}, "test")
        with self.assertRaises(ValueError):
            validate({"findings": [dict(self.item(), status="confirmed")]}, {}, "test")

    def test_malformed_model_output_retains_raw_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "sample.py").write_text("eval(x)")
            conn = MagicMock()
            conn.getresponse.return_value.status = 200
            conn.getresponse.return_value.read.return_value = b'{"message":{"content":"not json"}}'
            with patch("securevantara.local_llm.http.client.HTTPConnection", return_value=conn) as factory:
                result = review(directory)
            self.assertTrue(result["error"])
            self.assertIn("not json", result["raw_response"])
            factory.assert_called_once_with("127.0.0.1", 11434, timeout=120)
            self.assertEqual(result["findings"], [])
            payload = json.loads(conn.request.call_args.args[2])
            self.assertFalse(payload["stream"])
            self.assertNotIn("tools", payload)
            conn.close.assert_called_once()

    def test_successful_mocked_review_and_other_model(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "sample.py").write_text("eval(x)")
            conn = MagicMock()
            conn.getresponse.return_value.status = 200
            conn.getresponse.return_value.read.return_value = json.dumps({"message": {
                "content": json.dumps({"findings": [self.item()]})}}).encode()
            with patch("securevantara.local_llm.http.client.HTTPConnection", return_value=conn):
                result = review(directory, model="other:local")
            self.assertIsNone(result["error"])
            self.assertEqual(len(result["findings"]), 1)

    def test_model_name_and_limits(self):
        for model in ["", "bad model", "x\nfoo"]:
            with self.assertRaises(ValueError):
                review(".", model=model)
        with self.assertRaises(ValueError):
            review(".", timeout=float("nan"))

    def test_http_error_and_no_redirect(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "sample.py").write_text("eval(x)")
            conn = MagicMock()
            conn.getresponse.return_value.status = 302
            conn.getresponse.return_value.read.return_value = b''
            with patch("securevantara.local_llm.http.client.HTTPConnection", return_value=conn), self.assertRaises(ValueError):
                review(directory)
            self.assertEqual(conn.request.call_count, 1)

    def test_no_supported_sources(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            review(directory)
