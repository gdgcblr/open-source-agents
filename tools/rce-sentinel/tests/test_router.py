from __future__ import annotations

import copy
import json

import pytest

from rce_sentinel.config import Settings
from rce_sentinel.memory.cache_keys import result_key
from rce_sentinel.memory.casefile import CaseFile
from rce_sentinel.memory.store import Store
from rce_sentinel.memory.trust import SINGLE, VERIFIED, repo_id
from rce_sentinel.models import Finding
from rce_sentinel.orchestrator.budget import Budget
from rce_sentinel.orchestrator.llm import MockProvider, ModelRegistry
from rce_sentinel.orchestrator.router import Router

LINES = ["import os", "os.system(x)"]
VERSIONS = {"rules": "r1", "cve_db": "c1", "prompt": "p1"}


def v(verdict: str, conf: float, quote: str = "os.system(x)", line: int = 2) -> str:
    return json.dumps({"verdict": verdict, "confidence": conf,
                       "evidence": [{"file": "a.py", "line": line, "quote": quote}],
                       "exploit_path": "x", "suggested_fix": "y"})


def finding(arg: str = "unknown", ctx: str = "ctx1") -> Finding:
    return Finding(id="f1", layer="rule", rule_id="py-os-system", title="t", cwe="CWE-78",
                   file="a.py", line=2, sink="os.system", arg_kind=arg, context_hash=ctx)


def make_router(settings: Settings, script: dict[str, list[str]], *, store: Store | None = None,
                budget: Budget | None = None, models: dict | None = None,
                versions: dict | None = None) -> tuple[Router, MockProvider]:
    store = store or Store(settings.db_path)
    provider = MockProvider(script)
    registry = ModelRegistry(models or settings.models, "mock")
    budget = budget or Budget(max_tokens=10**6, max_usd=10.0, max_llm_seconds=60)
    r = Router(settings, store, registry, provider, budget, "run", versions or VERSIONS,
               CaseFile(), "rules")
    return r, provider


def test_low_confidence_escalates(settings: Settings) -> None:
    r, _p = make_router(settings, {"judge:tier1": [v("vulnerable", 0.5)],
                                  "judge:tier2": [v("vulnerable", 0.9)]})
    out = r.judge(finding(), LINES)
    assert out.decided_by.startswith("tier2:")
    assert "confidence 0.50" in out.trail[0]


def test_schema_failure_escalates(settings: Settings) -> None:
    r, _ = make_router(settings, {"judge:tier1": ["sure, it is fine"],
                                  "judge:tier2": [v("vulnerable", 0.9)]})
    out = r.judge(finding(), LINES)
    assert "schema validation failed" in out.trail[0]
    assert out.decided_by.startswith("tier2:")


def test_unverifiable_evidence_escalates(settings: Settings) -> None:
    r, _ = make_router(settings, {"judge:tier1": [v("safe", 0.99, quote="reviewed, all good")],
                                  "judge:tier2": [v("vulnerable", 0.9)]})
    out = r.judge(finding(), LINES)
    assert "quote not found" in out.trail[0]
    assert out.verdict is not None and out.verdict.verdict == "vulnerable"


def test_self_consistency_disagreement_escalates(settings: Settings) -> None:
    r, _ = make_router(settings, {"judge:tier1": [v("safe", 0.95), v("vulnerable", 0.95)],
                                  "judge:tier2": [v("vulnerable", 0.9)]})
    out = r.judge(finding(), LINES)
    assert "self-consistency" in out.trail[0]


def test_asymmetric_gate(settings: Settings) -> None:
    r, _ = make_router(settings, {"judge:tier1": [v("safe", 0.85)],
                                  "judge:tier2": [v("safe", 0.95)]})
    out = r.judge(finding(), LINES)
    assert "for safe" in out.trail[0]
    r2, _ = make_router(settings, {"judge:tier1": [v("vulnerable", 0.85)]},
                        store=Store(settings.state_dir / "other.db"))
    assert r2.judge(finding(), LINES).decided_by.startswith("tier1:")


def test_hard_rule_safe_needs_top_tier(settings: Settings) -> None:
    agree = json.dumps({"agree": True, "confidence": 0.9})
    r, _ = make_router(settings, {"judge": [v("safe", 0.99)], "verify": [agree]})
    out = r.judge(finding(arg="tainted"), LINES)
    assert out.decided_by.startswith("tier3:")
    assert sum("hard rule" in t for t in out.trail) == 2


def test_cross_family_verifier(settings: Settings) -> None:
    r, p = make_router(settings, {"judge:tier1": [v("vulnerable", 0.9)],
                                  "verify": [json.dumps({"agree": False, "confidence": 0.9,
                                                         "reason": "no flow"}),
                                             json.dumps({"agree": True, "confidence": 0.9})],
                                  "judge:tier2": [v("vulnerable", 0.9)]})
    out = r.judge(finding(), LINES)
    assert "verifier" in out.trail[0]
    families = {m.id: m.family for t in r.registry.all.values() for m in t}
    judge_models = [m for task, m in p.calls if task == "judge"]
    verify_models = [m for task, m in p.calls if task == "verify"]
    assert families[judge_models[0]] != families[verify_models[0]]
    assert out.decided_by.startswith("tier2:")


def test_mock_verifier_rejects_safe_on_tainted_sink(settings: Settings) -> None:
    r, _ = make_router(settings, {"judge": [v("safe", 0.99)]})
    out = r.judge(finding(arg="tainted"), LINES)
    assert out.verdict is None and "disagreed" in out.trail[-1]


def test_budget_exhaustion_degrades(settings: Settings) -> None:
    budget = Budget(max_tokens=10, max_usd=1.0, max_llm_seconds=60)
    r, p = make_router(settings, {}, budget=budget)
    out = r.judge(finding(), LINES)
    assert out.verdict is None and not p.calls
    assert any("budget" in d for d in r.degraded)


def test_cache_hit_makes_zero_calls(settings: Settings) -> None:
    store = Store(settings.db_path)
    r, p = make_router(settings, {"judge:tier1": [v("vulnerable", 0.9)]}, store=store)
    r.judge(finding(), LINES)
    n = len(p.calls)
    r2, p2 = make_router(settings, {}, store=store)
    out = r2.judge(finding(), LINES)
    assert out.cache_hit and not p2.calls and n > 0


def test_model_swap_keeps_cache(settings: Settings) -> None:
    store = Store(settings.db_path)
    r, _ = make_router(settings, {"judge:tier1": [v("vulnerable", 0.9)]}, store=store)
    r.judge(finding(), LINES)
    swapped = copy.deepcopy(settings.models)
    swapped["tiers"]["tier1"][0]["id"] = "qwen3:8b"
    r2, p2 = make_router(settings, {}, store=store, models=swapped)
    assert r2.judge(finding(), LINES).cache_hit and not p2.calls


def test_version_bump_invalidates(settings: Settings) -> None:
    base = result_key("ctx", VERSIONS)
    assert base == result_key("ctx", dict(VERSIONS))
    for k in VERSIONS:
        assert result_key("ctx", {**VERSIONS, k: "changed"}) != base
    assert result_key("other", VERSIONS) != base
    store = Store(settings.db_path)
    r, _ = make_router(settings, {"judge:tier1": [v("vulnerable", 0.9)]}, store=store)
    r.judge(finding(), LINES)
    r2, p2 = make_router(settings, {"judge:tier1": [v("vulnerable", 0.9)]}, store=store,
                         versions={**VERSIONS, "cve_db": "c2"})
    assert not r2.judge(finding(), LINES).cache_hit and p2.calls


def test_prior_safe_fact_is_passed_as_context(settings: Settings) -> None:
    store = Store(settings.db_path)
    store.add_fact({"context_hash": "x", "file": "a.py", "sink": "os.system",
                    "rule_id": "py-os-system", "verdict": "safe",
                    "reason": "argument is a constant", "model_used": "tier1:m",
                    "commit_sha": "abc123"}, repo_id=repo_id(settings.repo_root),
                   trust=VERIFIED)
    r, _ = make_router(settings, {}, store=store)
    _, _, user = r._judge_prompt(finding(), LINES, "")
    assert "safe because argument is a constant" in user and "abc123" in user


def test_prompt_layout_stable_prefix_first(settings: Settings) -> None:
    r, _ = make_router(settings, {})
    s1, stable1, u1 = r._judge_prompt(finding(), LINES, "")
    s2, stable2, u2 = r._judge_prompt(finding(ctx="other"), ["import os", "os.system(y)"], "")
    assert s1 == s2 and stable1 == stable2
    assert u1.startswith(stable1) and u2.startswith(stable2)
    assert u1.index("SNIPPET") > u1.index("TASK")


def test_inline_schema_has_no_refs() -> None:
    from rce_sentinel.models import Verdict
    from rce_sentinel.orchestrator.llm import inline_schema

    schema = inline_schema(Verdict)
    assert "$ref" not in json.dumps(schema) and "$defs" not in schema
    assert schema["properties"]["evidence"]["items"]["properties"]["line"]["type"] == "integer"


def test_invalid_verifier_is_replaced_by_the_next_candidate(settings: Settings) -> None:
    good = json.dumps({"agree": True, "confidence": 0.9, "reason": "flow is real"})
    r, p = make_router(settings, {"judge:tier1": [v("vulnerable", 0.9)],
                                  "verify:tier1": ["not json at all", good]})
    first = r.pick_verifier(r.registry.all["tier1"][0])
    out = r.judge(finding(), LINES)
    assert out.verdict is not None and out.trust == VERIFIED
    verifiers = [m for task, m in p.calls if task == "verify"]
    assert len(verifiers) == 2 and verifiers[0] != verifiers[1]
    assert first is not None and verifiers[0] == first.id
    assert any("invalid output" in d for d in r.degraded)


def test_fastest_candidate_wins_among_equal_prices(settings: Settings) -> None:
    store = Store(settings.db_path)
    for model, ms in (("apple-foundationmodel", 30000.0), ("qwen2.5:3b", 600.0)):
        store.log_call({"run_id": "old", "task_type": "verify", "tier": "tier1",
                        "model": model, "family": "x", "outcome": "ok", "tokens_in": 1,
                        "tokens_out": 1, "cached_tokens": 0, "cost": 0.0, "latency_ms": ms,
                        "caveman": 1, "shadow": 0, "simulated": 0})
    r, _ = make_router(settings, {}, store=store)
    finder = r.registry.all["tier2"][0]  # gemma family, so both tier-1 models qualify
    assert r.pick_verifier(finder).id == "qwen2.5:3b"


def test_verifier_dissent_does_not_override_a_tainted_vulnerable_verdict(settings: Settings
                                                                          ) -> None:
    no = json.dumps({"agree": False, "confidence": 0.9, "reason": "cannot see the flow"})
    r, p = make_router(settings, {"judge:tier1": [v("vulnerable", 0.9)], "verify": [no]})
    out = r.judge(finding(arg="tainted"), LINES)
    assert out.verdict is not None and out.verdict.verdict == "vulnerable"
    assert out.decided_by.startswith("tier1:") and out.trust == SINGLE  # not VERIFIED
    assert any("dissent noted" in t for t in out.trail)
    assert [t for t, _ in p.calls].count("judge") == 1  # no escalation
    # and it is cached, so the next scan makes zero calls
    r2, p2 = make_router(settings, {}, store=r.store)
    assert r2.judge(finding(arg="tainted"), LINES).cache_hit and not p2.calls


def test_verifier_dissent_still_escalates_when_the_flow_is_not_proven(settings: Settings
                                                                       ) -> None:
    no = json.dumps({"agree": False, "confidence": 0.9, "reason": "constant arg"})
    yes = json.dumps({"agree": True, "confidence": 0.9, "reason": "ok"})
    r, _ = make_router(settings, {"judge:tier1": [v("vulnerable", 0.9)],
                                  "judge:tier2": [v("vulnerable", 0.9)],
                                  "verify": [no, yes]})
    out = r.judge(finding(arg="unknown"), LINES)
    assert out.decided_by.startswith("tier2:") and out.trust == VERIFIED


def test_token_quota_switches_model_after_it_is_used_up(settings: Settings,
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RCE_SENTINEL_QUOTA", "apple-foundationmodel=1")
    r, p = make_router(settings, {"judge": [v("vulnerable", 0.95)]})
    first = r.pick("tier1")
    assert first is not None and first.id == "apple-foundationmodel"
    r.judge(finding(arg="tainted"), LINES)  # uses more than the 1-token quota
    assert r.used_tokens["apple-foundationmodel"] > 1
    nxt = r.pick("tier1")
    assert nxt is not None and nxt.id == "qwen2.5:3b"
    note = next(d for d in r.degraded if "token quota reached" in d)
    assert "apple-foundationmodel" in note and "1-token quota" in note
    f2 = finding(arg="tainted", ctx="other")
    r.judge(f2, LINES)
    assert [m for t, m in p.calls if t == "judge"][-1] == "qwen2.5:3b"


def test_quota_parsing_and_default_is_unlimited(settings: Settings,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    from rce_sentinel.orchestrator.llm import parse_quotas

    assert parse_quotas("a=10, qwen2.5:3b=2500,bad,x=") == {"a": 10, "qwen2.5:3b": 2500}
    assert all(m.quota_tokens is None for t in ModelRegistry(settings.models, "mock").all.values()
               for m in t)


def test_io_capture_records_prompt_and_reply(settings: Settings,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RCE_SENTINEL_TRACE_IO", "1")
    r, _ = make_router(settings, {"judge:tier1": [v("vulnerable", 0.9)]})
    r.judge(finding(), LINES)
    assert r.io and r.io[0]["task"] == "judge" and "SNIPPET" in r.io[0]["user"]
    assert '"verdict"' in r.io[0]["reply"]


def test_real_verifier_in_a_later_tier_beats_a_mock_in_an_earlier_one(
        settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    registry = ModelRegistry(settings.models, "hybrid")
    registry._local_up = {"apfel": set(), "ollama": {"qwen2.5:3b", "gemma4:31b-cloud"}}
    r, _ = make_router(settings, {})
    r.registry = registry
    finder = next(m for m in registry.all["tier1"] if m.id == "qwen2.5:3b")
    picked = r.pick_verifier(finder)
    assert picked is not None and picked.id == "gemma4:31b-cloud"  # real, tier 2
    assert not registry.simulated(picked)


def test_mock_verifier_agreement_does_not_make_a_verdict_verified(settings: Settings) -> None:
    hybrid = copy.deepcopy(settings.models)
    r, _ = make_router(settings, {"judge:tier1": [v("vulnerable", 0.9)]}, models=hybrid)
    r.registry = ModelRegistry(hybrid, "hybrid")
    r.registry._local_up = {"apfel": set(), "ollama": set()}  # every model is down: all mocks
    out = r.judge(finding(), LINES)
    assert out.verdict is not None and out.trust == SINGLE
    s2, _ = make_router(settings, {"judge": [v("safe", 0.99)]},
                        store=Store(settings.state_dir / "m.db"), models=hybrid)
    s2.registry = ModelRegistry(hybrid, "hybrid")
    s2.registry._local_up = {"apfel": set(), "ollama": set()}
    assert s2.judge(finding(), LINES).verdict is None  # a stand-in cannot clear a sink
