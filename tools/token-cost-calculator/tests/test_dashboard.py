"""Unit tests for cost analytics HTML dashboard."""

import os
import tempfile
import pytest
from calculator.analyzer import analyze_token_costs
from calculator.dashboard import generate_cost_dashboard_html


def test_cost_dashboard_generation():
    with tempfile.TemporaryDirectory() as tmpdir:
        report_file = os.path.join(tmpdir, "cost_report.html")
        report = analyze_token_costs("Sample prompt for testing dashboard generation.")

        html_out = generate_cost_dashboard_html(report, report_file)
        assert os.path.exists(report_file)
        assert "<!DOCTYPE html>" in html_out
        assert "Token Usage &amp; Cost Calculator" in html_out or "Token Usage & Cost Calculator" in html_out
        assert "gemini-2.5-flash" in html_out
        assert "Best Value" in html_out


def test_dashboard_xss_protection():
    with tempfile.TemporaryDirectory() as tmpdir:
        report_file = os.path.join(tmpdir, "xss_cost_report.html")
        xss_label = "<script>alert('xss')</script>"
        report = analyze_token_costs("Prompt", source_label=xss_label)

        html_out = generate_cost_dashboard_html(report, report_file)
        # Check unescaped script tag is not present outside json script payload
        assert "<script>alert('xss')</script>" not in html_out.split('<script id="cost-data-payload"')[0]
