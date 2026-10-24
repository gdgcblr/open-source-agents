"""Tests for safely rendering external repository data in HTML reports."""

import tempfile
import unittest
from pathlib import Path

from main import generate_html_report


class TestReportSafety(unittest.TestCase):
    def test_escapes_untrusted_text_and_rejects_non_github_links(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "report.html"
            generate_html_report(
                [{
                    "full_name": "<script>alert(1)</script>",
                    "html_url": "javascript:alert(1)",
                    "clone_url": "javascript:alert(1)",
                    "description": "<img src=x onerror=alert(1)>",
                }],
                "<script>",
                "<script>",
                str(report_path),
            )
            report = report_path.read_text(encoding="utf-8")

        self.assertIn("&lt;script&gt;", report)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", report)
        self.assertNotIn('href="javascript:', report)
        self.assertNotIn("onclick=", report)


if __name__ == "__main__":
    unittest.main()
