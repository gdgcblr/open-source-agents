"""Unit tests for cost analyzer and multi-model comparison."""

import pytest
from calculator.analyzer import analyze_token_costs


def test_analyze_multi_model():
    text = "Analyze this sample code snippet and find bugs."
    report = analyze_token_costs(text, primary_model_id="gemini-2.5-flash")

    assert report.breakdown.total_tokens > 0
    assert report.primary_estimate.model_id == "gemini-2.5-flash"
    assert len(report.comparisons) >= 8
    assert report.cheapest_model_id in [c.model_id for c in report.comparisons]
    assert report.max_savings_percentage >= 0.0


def test_custom_comparison_list():
    text = "Short query."
    custom_models = ["gemini-2.5-flash", "gpt-4o", "claude-3-5-sonnet"]
    report = analyze_token_costs(text, primary_model_id="gpt-4o", compare_models=custom_models)

    assert len(report.comparisons) == 3
    assert any(c.model_id == "gemini-2.5-flash" for c in report.comparisons)
