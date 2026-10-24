"""Unit tests for deterministic code review and risk analysis."""

import unittest
from agentrelay.code_review import parse_unified_diff, run_deterministic_review


class TestCodeReview(unittest.TestCase):
    """Test diff parser and deterministic risk rules."""

    def test_parse_unified_diff(self):
        patch = (
            "diff --git a/services/auth.py b/services/auth.py\n"
            "index 0000000..1111111 100644\n"
            "--- a/services/auth.py\n"
            "+++ b/services/auth.py\n"
            "@@ -10,3 +10,4 @@\n"
            " def login():\n"
            "+    token = 'secret'\n"
            "     return True\n"
        )
        files = parse_unified_diff(patch)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].new_path, "services/auth.py")
        self.assertEqual(len(files[0].hunks), 1)
        self.assertEqual(len(files[0].hunks[0].added_lines), 1)
        self.assertEqual(files[0].hunks[0].added_lines[0][0], 11)

    def test_detect_hardcoded_secrets(self):
        patch = (
            "diff --git a/config.py b/config.py\n"
            "--- a/config.py\n"
            "+++ b/config.py\n"
            "@@ -1,2 +1,3 @@\n"
            "+AWS_KEY = 'AKIA1234567890ABCDEF'\n"
        )
        report, ev_store = run_deterministic_review(patch)
        claims = [f.claim for f in report.findings]
        self.assertTrue(any("Hardcoded Secret" in c for c in claims))
        self.assertTrue(any(f.severity == "critical" for f in report.findings))

    def test_detect_command_injection(self):
        patch = (
            "diff --git a/tasks.py b/tasks.py\n"
            "--- a/tasks.py\n"
            "+++ b/tasks.py\n"
            "@@ -1,2 +1,3 @@\n"
            "+subprocess.run(f'convert {user_img}', shell=True)\n"
        )
        report, ev_store = run_deterministic_review(patch)
        claims = [f.claim for f in report.findings]
        self.assertTrue(any("Shell Command Execution" in c for c in claims))

    def test_detect_missing_tests(self):
        patch = (
            "diff --git a/core/pricing.py b/core/pricing.py\n"
            "--- a/core/pricing.py\n"
            "+++ b/core/pricing.py\n"
            "@@ -1,2 +1,3 @@\n"
            "+def calculate_discount(price): return price * 0.8\n"
        )
        report, ev_store = run_deterministic_review(patch)
        claims = [f.claim for f in report.findings]
        self.assertTrue(any("without accompanying unit or integration tests" in c for c in claims))

    def test_clean_diff_with_tests_has_no_findings(self):
        patch = (
            "diff --git a/calc.py b/calc.py\n"
            "--- a/calc.py\n"
            "+++ b/calc.py\n"
            "@@ -1,2 +1,3 @@\n"
            "+def multiply(x, y): return x * y\n"
            "diff --git a/tests/test_calc.py b/tests/test_calc.py\n"
            "--- a/tests/test_calc.py\n"
            "+++ b/tests/test_calc.py\n"
            "@@ -1,2 +1,3 @@\n"
            "+def test_multiply(): assert multiply(2, 4) == 8\n"
        )
        report, ev_store = run_deterministic_review(patch)
        self.assertEqual(len(report.findings), 0)

    def test_malformed_diff_safety(self):
        # Must not raise exception on random binary or corrupt text
        report, ev_store = run_deterministic_review("GARBAGE TEXT NOT A DIFF")
        self.assertEqual(len(report.findings), 0)
        self.assertTrue(any("empty or unsupported diff" in report.summary for _ in [1]))

    def test_plain_code_snippet_support(self):
        # Users can paste plain code directly without git diff headers
        code = "query = f'SELECT * FROM accounts WHERE user_id = {uid}'\n"
        report, ev_store = run_deterministic_review(code)
        claims = [f.claim for f in report.findings]
        self.assertTrue(any("SQL Query" in c for c in claims))



if __name__ == "__main__":
    unittest.main()
