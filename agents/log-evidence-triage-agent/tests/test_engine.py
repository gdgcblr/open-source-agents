"""Standard library tests; no third-party packages or model key needed."""
import unittest
from pathlib import Path

from incident_triage.engine import analyze_logs, redact, get_runbook, MAX_BYTES
from incident_triage.tools import triage_log_file


class TriageEngineTests(unittest.TestCase):
    def setUp(self):
        self.sample = (Path(__file__).resolve().parents[1] / "samples" / "spring-boot-incident.log").read_text()

    def test_pool_exhaustion_is_ranked_above_symptoms(self):
        result = analyze_logs(self.sample)
        self.assertEqual(result["top_signals"][0]["id"], "database_pool_exhaustion")
        self.assertEqual(result["status"], "signals_detected")
        self.assertEqual(result["top_signals"][0]["evidence"][0]["line"], 4)

    def test_timeline_is_ordered_by_log_line(self):
        timeline = analyze_logs(self.sample)["timeline"]
        self.assertEqual([x["line"] for x in timeline], sorted(x["line"] for x in timeline))

    def test_redact_secrets(self):
        redacted = redact('password=oops api_key=abc Authorization: Bearer ey.ab.cd https://bob:mypass@db:5432')
        for secret in ("oops", "abc", "ey.ab.cd", "mypass"):
            self.assertNotIn(secret, redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_unknown_log_does_not_fabricate_root_cause(self):
        result = analyze_logs("2026-10-24 11:11:11 INFO boot okay")
        self.assertIsNone(result["probable_root_cause"])
        self.assertEqual(result["status"], "no_known_signals")

    def test_max_size(self):
        with self.assertRaises(ValueError):
            analyze_logs("x" * (MAX_BYTES + 1))

    def test_runbook_is_safe(self):
        data = get_runbook("database_pool_exhaustion")
        self.assertGreater(len(data["checks"]), 0)
        self.assertIn("Manual verification", data["note"])

    def test_guard_against_path_traversal(self):
        self.assertIn("outside", triage_log_file("../../README.md")["error"])

    def test_sample_file_tool(self):
        result = triage_log_file("spring-boot-incident.log")
        self.assertEqual(result["source_file"], "spring-boot-incident.log")
        self.assertEqual(result["top_signals"][0]["id"], "database_pool_exhaustion")


if __name__ == "__main__":
    unittest.main()
