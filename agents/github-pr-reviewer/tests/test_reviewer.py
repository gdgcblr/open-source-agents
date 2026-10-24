import os
import sys
import unittest

# Ensure agent package root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pr_agent.diff_parser import parse_unified_diff
from pr_agent.rules import calculate_triage
from pr_agent.reviewer import PRReviewerAgent
from pr_agent.github_client import parse_pr_target, load_diff_from_file
from pr_agent.specialists import SecurityAuditorAgent, PerformanceArchitectAgent, AutoTestGeneratorAgent, LeadArchitectAgent
from pr_agent.patch_generator import AutoPatchGenerator
from pr_agent.html_reporter import generate_html_dashboard


class TestPRReviewerCouncil(unittest.TestCase):

    def setUp(self):
        self.samples_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "samples")
        self.sample_diff_path = os.path.join(self.samples_dir, "sample_pr_diff.patch")
        self.sample_bug_path = os.path.join(self.samples_dir, "sample_bug_fix.patch")

    def test_parse_pr_target(self):
        parsed = parse_pr_target("https://github.com/torvalds/linux/pull/42")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed, ("torvalds", "linux", 42))

        parsed_slug = parse_pr_target("facebook/react#1234")
        self.assertIsNotNone(parsed_slug)
        self.assertEqual(parsed_slug, ("facebook", "react", 1234))

        self.assertIsNone(parse_pr_target("invalid-target-format"))

    def test_parse_unified_diff(self):
        diff_text, _ = load_diff_from_file(self.sample_diff_path)
        file_diffs = parse_unified_diff(diff_text)
        self.assertEqual(len(file_diffs), 2)
        self.assertEqual(file_diffs[0].filename, "src/auth/service.py")
        self.assertGreater(file_diffs[0].additions, 0)
        self.assertGreater(file_diffs[0].deletions, 0)
        self.assertEqual(file_diffs[1].filename, "src/config.py")

    def test_security_specialist_agent(self):
        diff_text, _ = load_diff_from_file(self.sample_diff_path)
        file_diffs = parse_unified_diff(diff_text)
        sec_agent = SecurityAuditorAgent()
        verdict = sec_agent.evaluate(file_diffs)

        self.assertEqual(verdict.status, "FAILED")
        self.assertLess(verdict.score, 60)
        cwe_ids = [f.cwe_id for f in verdict.findings if f.cwe_id]
        self.assertTrue(any("CWE-798" in cwe for cwe in cwe_ids))
        self.assertTrue(any("CWE-89" in cwe for cwe in cwe_ids))

    def test_performance_specialist_agent(self):
        diff_text, _ = load_diff_from_file(self.sample_diff_path)
        file_diffs = parse_unified_diff(diff_text)
        perf_agent = PerformanceArchitectAgent()
        verdict = perf_agent.evaluate(file_diffs)

        self.assertIsNotNone(verdict)
        self.assertIn("Resource", verdict.summary)

    def test_auto_test_generator_agent(self):
        diff_text, _ = load_diff_from_file(self.sample_diff_path)
        file_diffs = parse_unified_diff(diff_text)
        test_agent = AutoTestGeneratorAgent()
        verdict, generated_tests = test_agent.evaluate(file_diffs)

        self.assertGreaterEqual(len(generated_tests), 1)
        # authenticate_user was defined in src/auth/service.py
        self.assertTrue(any("authenticate_user" in t.test_name for t in generated_tests))
        self.assertIn("def test_authenticate_user", generated_tests[0].code)

    def test_auto_patch_generator(self):
        diff_text, _ = load_diff_from_file(self.sample_diff_path)
        file_diffs = parse_unified_diff(diff_text)
        sec_agent = SecurityAuditorAgent()
        verdict = sec_agent.evaluate(file_diffs)

        patch = AutoPatchGenerator.generate_remediation_patch(file_diffs, verdict.findings)
        self.assertIsNotNone(patch)
        self.assertIn("diff --git a/src/auth/service.py", patch)
        self.assertIn("os.environ.get", patch)

    def test_html_dashboard_generation(self):
        agent = PRReviewerAgent(offline=True)
        diff_text, _ = load_diff_from_file(self.sample_diff_path)
        report = agent.analyze(diff_text, "Sample PR")
        html = generate_html_dashboard(report)

        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("PR Review Dashboard", html)
        self.assertIn("Specialist Agent Council Scorecard", html)
        self.assertIn(str(report.health_score), html)

    def test_end_to_end_council_verdict_blocked(self):
        diff_text, _ = load_diff_from_file(self.sample_diff_path)
        agent = PRReviewerAgent(offline=True)
        report = agent.analyze(diff_text, "Vulnerable PR")

        self.assertEqual(report.verdict, "BLOCKED")
        self.assertLess(report.health_score, 60)
        self.assertEqual(len(report.specialist_reviews), 3)
        self.assertIsNotNone(report.remediation_patch)

    def test_end_to_end_council_verdict_approved(self):
        diff_text, _ = load_diff_from_file(self.sample_bug_path)
        agent = PRReviewerAgent(offline=True)
        report = agent.analyze(diff_text, "Clean Bug Fix")

        self.assertIn(report.verdict, ("APPROVED", "CHANGES_REQUESTED"))
        self.assertGreaterEqual(report.health_score, 70)
        self.assertEqual(report.triage.pr_type, "Bug Fix")

    def test_self_healing_verification(self):
        from pr_agent.self_healing import SelfHealingEngine
        diff_text, _ = load_diff_from_file(self.sample_diff_path)
        agent = PRReviewerAgent(offline=True)
        report = agent.analyze(diff_text, "Vulnerable PR")

        # Verify initial is BLOCKED
        self.assertEqual(report.verdict, "BLOCKED")

        orig_diffs = parse_unified_diff(diff_text)
        healed_diffs = SelfHealingEngine.apply_patch_to_diffs(orig_diffs, report.remediation_patch)
        sec_healed = agent.security_agent.evaluate(healed_diffs)
        self.assertGreater(sec_healed.score, 50)


if __name__ == "__main__":
    unittest.main()
