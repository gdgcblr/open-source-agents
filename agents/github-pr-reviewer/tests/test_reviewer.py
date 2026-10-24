import os
import sys
import unittest

# Ensure agent package root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pr_agent.diff_parser import parse_unified_diff
from pr_agent.rules import run_heuristic_checks, calculate_triage
from pr_agent.reviewer import PRReviewerAgent
from pr_agent.github_client import parse_pr_target, load_diff_from_file


class TestPRReviewer(unittest.TestCase):

    def setUp(self):
        self.samples_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "samples")
        self.sample_diff_path = os.path.join(self.samples_dir, "sample_pr_diff.patch")
        self.sample_bug_path = os.path.join(self.samples_dir, "sample_bug_fix.patch")

    def test_parse_pr_target(self):
        # URL format
        parsed = parse_pr_target("https://github.com/torvalds/linux/pull/42")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed, ("torvalds", "linux", 42))

        # Slug format
        parsed_slug = parse_pr_target("facebook/react#1234")
        self.assertIsNotNone(parsed_slug)
        self.assertEqual(parsed_slug, ("facebook", "react", 1234))

        # Invalid format
        self.assertIsNone(parse_pr_target("just-some-random-string"))

    def test_parse_unified_diff(self):
        diff_text, _ = load_diff_from_file(self.sample_diff_path)
        file_diffs = parse_unified_diff(diff_text)

        self.assertEqual(len(file_diffs), 2)
        self.assertEqual(file_diffs[0].filename, "src/auth/service.py")
        self.assertGreater(file_diffs[0].additions, 0)
        self.assertGreater(file_diffs[0].deletions, 0)
        self.assertEqual(file_diffs[1].filename, "src/config.py")

    def test_heuristic_security_detection(self):
        diff_text, _ = load_diff_from_file(self.sample_diff_path)
        file_diffs = parse_unified_diff(diff_text)
        issues = run_heuristic_checks(file_diffs)

        # Check for AWS secret detection
        aws_issues = [i for i in issues if "AWS Access Key" in i.title]
        self.assertGreaterEqual(len(aws_issues), 1)
        self.assertEqual(aws_issues[0].severity, "CRITICAL")

        # Check for hardcoded secret detection
        secret_issues = [i for i in issues if "Potential hardcoded secret" in i.title]
        self.assertGreaterEqual(len(secret_issues), 1)

        # Check for SQL injection detection
        sql_issues = [i for i in issues if "SQL injection" in i.title]
        self.assertGreaterEqual(len(sql_issues), 1)
        self.assertEqual(sql_issues[0].severity, "HIGH")

    def test_calculate_triage(self):
        diff_text, _ = load_diff_from_file(self.sample_diff_path)
        file_diffs = parse_unified_diff(diff_text)
        issues = run_heuristic_checks(file_diffs)
        triage = calculate_triage(file_diffs, issues)

        self.assertEqual(triage.total_files, 2)
        self.assertEqual(triage.risk_level, "Critical")
        self.assertIn("CRITICAL", triage.summary.upper())

    def test_end_to_end_offline_analysis(self):
        diff_text, _ = load_diff_from_file(self.sample_bug_path)
        agent = PRReviewerAgent(offline=True)
        report = agent.analyze(diff_text, "Bug Fix Sample")

        self.assertEqual(report.title, "Bug Fix Sample")
        self.assertEqual(report.triage.pr_type, "Bug Fix")
        self.assertEqual(report.triage.size_tier, "XS")
        self.assertEqual(report.triage.risk_level, "Low")

        # Verify markdown output contains key sections
        md = report.to_markdown()
        self.assertIn("# 🤖 Pull Request Review & Triage Report", md)
        self.assertIn("## 📊 Triage Summary", md)
        self.assertIn("## 📝 Executive Summary", md)
        self.assertIn("## ✅ Reviewer Checklist", md)

        # Verify dict export
        data = report.to_dict()
        self.assertIn("triage", data)
        self.assertEqual(data["triage"]["size_tier"], "XS")


if __name__ == "__main__":
    unittest.main()
