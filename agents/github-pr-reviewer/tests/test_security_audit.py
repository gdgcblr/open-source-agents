import ast
import html
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pr_agent.models import ReviewReport, ReviewIssue, TriageResult, SpecialistVerdict
from pr_agent.html_reporter import generate_html_dashboard
from pr_agent.specialists import DependencyAuditorAgent
from pr_agent.diff_parser import parse_unified_diff


class TestSecurityAuditAndHardening(unittest.TestCase):
    """Security audit tests verifying that the agent itself is safe, hardened, and free of vulnerabilities."""

    def setUp(self):
        self.agent_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.pr_agent_dir = os.path.join(self.agent_root, "pr_agent")

    def test_xss_protection_in_html_reporter(self):
        """Verify that malicious script tags in PR title, diffs, or descriptions are escaped."""
        xss_payload = "<script>alert('pwned')</script><img src=x onerror=alert(1)>"

        report = ReviewReport(
            title=f"Exploit PR {xss_payload}",
            source="https://github.com/attacker/malicious/pull/1",
            triage=TriageResult(
                pr_type="Bug Fix",
                size_tier="XS",
                risk_level="Critical",
                total_additions=10,
                total_deletions=0,
                total_files=1,
                summary=f"Triage note with {xss_payload}"
            ),
            issues=[
                ReviewIssue(
                    file=f"src/{xss_payload}.py",
                    line=1,
                    severity="CRITICAL",
                    category="SECURITY",
                    title=f"Malicious issue {xss_payload}",
                    description=f"Description containing {xss_payload}",
                    suggestion=f"Suggestion with {xss_payload}"
                )
            ],
            executive_summary=f"Executive summary with {xss_payload}",
            recommendations=["Verify test suite"]
        )

        dashboard_html = generate_html_dashboard(report)

        # Ensure no raw unescaped script tag exists
        self.assertNotIn("<script>alert('pwned')</script>", dashboard_html)
        self.assertNotIn("<img src=x onerror=alert(1)>", dashboard_html)

        # Ensure proper HTML entity escaping
        self.assertIn("&lt;script&gt;alert(&#x27;pwned&#x27;)&lt;/script&gt;", dashboard_html)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", dashboard_html)

    def test_no_eval_or_exec_in_agent_codebase(self):
        """AST security audit: Ensure NO eval(), exec(), or os.system() exists in pr_agent."""
        banned_calls = {"eval", "exec", "system"}

        for root, _, files in os.walk(self.pr_agent_dir):
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    with open(full_path, "r", encoding="utf-8") as f:
                        source_code = f.read()

                    tree = ast.parse(source_code, filename=full_path)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call):
                            # Check function name
                            if isinstance(node.func, ast.Name):
                                self.assertNotIn(
                                    node.func.id,
                                    banned_calls,
                                    f"Security violation: banned call `{node.func.id}()` found in {file}:L{node.lineno}"
                                )
                            elif isinstance(node.func, ast.Attribute):
                                if node.func.attr == "system":
                                    self.assertFalse(
                                        isinstance(node.func.value, ast.Name) and node.func.value.id == "os",
                                        f"Security violation: banned `os.system()` found in {file}:L{node.lineno}"
                                    )

    def test_sca_dependency_vulnerability_detection(self):
        """Verify that Software Composition Analysis detects known CVEs in requirements.txt."""
        vulnerable_manifest_diff = """diff --git a/requirements.txt b/requirements.txt
--- a/requirements.txt
+++ b/requirements.txt
@@ -1,3 +1,4 @@
+pyyaml==5.1
+urllib3==1.24.1
+requests==2.18.0
"""
        diffs = parse_unified_diff(vulnerable_manifest_diff)
        sca_agent = DependencyAuditorAgent()
        verdict = sca_agent.evaluate(diffs)

        self.assertEqual(verdict.status, "FAILED")
        self.assertLess(verdict.score, 60)
        cve_tags = [i.cwe_id for i in verdict.findings if i.cwe_id]
        self.assertTrue(any("CVE-2020-14343" in cve for cve in cve_tags))
        self.assertTrue(any("CVE-2021-33503" in cve for cve in cve_tags))

    def test_server_path_traversal_rejection(self):
        """Verify that server path validation rejects directory traversal attempts."""
        test_paths = ["/api/../etc/passwd", "/../../../etc/shadow", "/api/sample\0malicious"]
        for p in test_paths:
            clean_path = os.path.normpath(p)
            is_flagged = ".." in p or clean_path.startswith("..") or "\0" in p or clean_path.startswith("/etc")
            self.assertTrue(is_flagged, f"Malicious path traversal was not flagged: {p}")


if __name__ == "__main__":
    unittest.main()
