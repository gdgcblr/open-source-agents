"""Unit tests for HTML report generator."""

import os
import tempfile
import pytest
from linter.template_linter import PromptLinter
from linter.dashboard import generate_lint_dashboard_html


def test_html_dashboard_generation():
    with tempfile.TemporaryDirectory() as tmpdir:
        report_file = os.path.join(tmpdir, "report.html")
        linter = PromptLinter()
        report = linter.lint("Hello {user}!", variables={"user": "Dave"})

        html_out = generate_lint_dashboard_html(report, report_file)
        assert os.path.exists(report_file)
        assert "<!DOCTYPE html>" in html_out
        assert "Prompt Context Linter" in html_out
        assert "LINT PASSED" in html_out
        assert "Dave" in html_out


def test_dashboard_xss_protection():
    with tempfile.TemporaryDirectory() as tmpdir:
        report_file = os.path.join(tmpdir, "xss_report.html")
        linter = PromptLinter()
        xss_template = "<script>alert('xss')</script> {val}"
        report = linter.lint(xss_template, variables={"val": "<b>safe</b>"}, template_name="<svg onload=alert(1)>")

        html_out = generate_lint_dashboard_html(report, report_file)
        # Check raw unescaped script tag is not present outside json payload
        assert "<script>alert('xss')</script>" not in html_out.split('<script id="linter-data-payload"')[0]
        assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in html_out or "&lt;script&gt;" in html_out
