import pytest

from cost_tracker import store
from cost_tracker.pricing import calculate_cost, resolve_model, load_pricing


def test_basic_cost():
    r = calculate_cost("gemini-2.5-flash", 1_000_000, 1_000_000)  # 0.30 + 2.50
    assert r["cost_usd"] == pytest.approx(2.80)


def test_thinking_billed_as_output():
    r = calculate_cost("gemini-2.5-flash", 0, 0, thinking_tokens=1_000_000)
    assert r["cost_usd"] == pytest.approx(2.50)


def test_cached_discount():
    full = calculate_cost("gemini-2.5-flash", 1_000_000, 0)["cost_usd"]
    cached = calculate_cost("gemini-2.5-flash", 1_000_000, 0, cached_tokens=1_000_000)["cost_usd"]
    assert cached == pytest.approx(full * 0.1)


def test_long_context_tier():
    short = calculate_cost("gemini-2.5-pro", 100_000, 0)["cost_usd"]
    long_ = calculate_cost("gemini-2.5-pro", 300_000, 0)["cost_usd"]
    assert long_ / 300_000 == pytest.approx(2 * short / 100_000)


def test_resolve_prefers_longest_prefix():
    t = load_pricing()
    assert resolve_model("models/gemini-2.5-flash-lite-001", t) == "gemini-2.5-flash-lite"
    assert resolve_model("gemini-2.5-flash-preview-09", t) == "gemini-2.5-flash"


def test_unknown_model():
    assert calculate_cost("gpt-99", 10, 10)["known_model"] is False


def test_store_and_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACKER_DB_PATH", str(tmp_path / "t.db"))
    from cost_tracker import tools
    for _ in range(4):
        c = calculate_cost("gemini-2.5-pro", 5000, 500, 2000)
        store.record("t", c["model"], 5000, 500, 2000, 0, c["cost_usd"], prompt_hash="abc")
    rep = tools.get_usage_report(7)
    assert rep["calls"] == 4 and rep["by_model"][0]["model"] == "gemini-2.5-pro"
    types = {t["type"] for t in tools.suggest_optimizations(7)["tips"]}
    assert {"downgrade_model", "reduce_thinking", "use_context_caching"} <= types
    tools.set_budget(0.001)
    assert tools.check_budget()["over_budget"] is True
