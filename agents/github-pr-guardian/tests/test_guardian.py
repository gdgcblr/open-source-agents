"""Unit test suite for GitHub PR Guardian."""

import sys
from pathlib import Path
import unittest

# Ensure agents/github-pr-guardian is on sys.path
AGENT_ROOT = Path(__file__).resolve().parent.parent
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from guardian.diff_parser import parse_unified_diff
from guardian.rules_scanner import RulesScanner
from guardian.agent import GuardianAgent


SAMPLE_VULN_DIFF = """diff --git a/app.py b/app.py
new file mode 100644
--- /dev/null
+++ b/app.py
@@ -0,0 +1,6 @@
+AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
+def run_code(raw_input):
+    return eval(raw_input)
+def find_user(name):
+    return f"SELECT * FROM users WHERE name = '{name}'"
"""


class TestDiffParser(unittest.TestCase):
    def test_parse_diff(self):
        files = parse_unified_diff(SAMPLE_VULN_DIFF)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].filename, "app.py")
        self.assertTrue(files[0].is_new)
        self.assertEqual(len(files[0].added_lines()), 5)


class TestRulesScanner(unittest.TestCase):
    def test_detect_secrets_and_vulns(self):
        files = parse_unified_diff(SAMPLE_VULN_DIFF)
        scanner = RulesScanner()
        findings = scanner.scan_files(files)

        titles = [f.title for f in findings]
        self.assertTrue(any("AWS Access Key" in t for t in titles))
        self.assertTrue(any("Arbitrary Code Execution" in t for t in titles))
        self.assertTrue(any("SQL Injection" in t for t in titles))


class TestGuardianAgent(unittest.TestCase):
    def test_static_review_pipeline(self):
        agent = GuardianAgent()
        review, findings = agent.review_diff_text(SAMPLE_VULN_DIFF, use_llm=False)
        self.assertEqual(review["verdict"], "REQUEST_CHANGES")
        self.assertGreaterEqual(review["risk_score"], 60)
        self.assertTrue(len(findings) >= 3)


if __name__ == "__main__":
    unittest.main()
