"""Unit tests for pricing registry and calculation."""

import pytest
from calculator.pricing import (
    PRICING_REGISTRY,
    estimate_model_cost,
    get_model_pricing,
    list_supported_models,
)


def test_list_supported_models():
    models = list_supported_models()
    assert len(models) >= 8
    assert "gemini-2.5-flash" in models
    assert "gpt-4o" in models
    assert "claude-3-5-sonnet" in models


def test_pricing_lookup_case_insensitive():
    p1 = get_model_pricing("gemini-2.5-flash")
    p2 = get_model_pricing("GEMINI-2.5-FLASH")
    assert p1 is not None
    assert p1 == p2
    assert p1.provider == "Google"


def test_cost_calculation_math():
    # 1,000,000 prompt tokens + 1,000,000 completion tokens on GPT-4o
    # Rate: $2.50 / 1M in, $10.00 / 1M out
    est = estimate_model_cost("gpt-4o", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert est.prompt_cost_usd == 2.50
    assert est.completion_cost_usd == 10.00
    assert est.total_cost_usd == 12.50


def test_context_window_fit():
    # 50,000 tokens fits in Gemini 1M window
    est = estimate_model_cost("gemini-2.5-flash", prompt_tokens=50_000, completion_tokens=10_000)
    assert est.fits_context_window is True

    # 150,000 tokens exceeds GPT-4o 128k window
    est2 = estimate_model_cost("gpt-4o", prompt_tokens=140_000, completion_tokens=20_000)
    assert est2.fits_context_window is False
