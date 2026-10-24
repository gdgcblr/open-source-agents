"""A model that fails authentication is dropped, the user is told, and the tier moves on."""

from __future__ import annotations

import json

import httpx
import pytest

from rce_sentinel.config import Settings
from rce_sentinel.memory.casefile import CaseFile
from rce_sentinel.memory.store import Store
from rce_sentinel.models import Finding
from rce_sentinel.orchestrator.budget import Budget
from rce_sentinel.orchestrator.llm import LLMResult, MockProvider, ModelRegistry, ModelSpec
from rce_sentinel.orchestrator.router import Router

CLOUD = "gemma4:31b-cloud"
LINES = ["import os", "os.system(x)"]


class Unauthorized(MockProvider):
    """Mock that answers 401 for the given model ids, like Ollama cloud before signin."""

    def __init__(self, bad: set[str], status: int = 401):
        super().__init__()
        self.bad, self.status = bad, status
        self.attempts: dict[str, int] = {}

    def complete(self, spec: ModelSpec, system: str, user: str, **kw) -> LLMResult:
        self.attempts[spec.id] = self.attempts.get(spec.id, 0) + 1
        if spec.id in self.bad:
            req = httpx.Request("POST", "http://127.0.0.1:11436/v1/chat/completions")
            resp = httpx.Response(self.status, request=req, json={"error": "Unauthorized"})
            raise httpx.HTTPStatusError("unauthorized", request=req, response=resp)
        return super().complete(spec, system, user, **kw)


def _router(settings: Settings, provider: MockProvider) -> Router:
    registry = ModelRegistry(settings.models, "mock")
    return Router(settings, Store(settings.db_path), registry, provider,
                  Budget(max_tokens=10**6, max_usd=10, max_llm_seconds=60), "run",
                  {"rules": "r", "cve_db": "c", "prompt": "p"}, CaseFile(), "rules")


def _finding(arg: str = "unknown") -> Finding:
    return Finding(id="f", layer="rule", rule_id="py-os-system", title="t", cwe="CWE-78",
                   file="a.py", line=2, sink="os.system", arg_kind=arg, context_hash="c")


def _ok(verdict: str, conf: float) -> str:
    return json.dumps({"verdict": verdict, "confidence": conf,
                       "evidence": [{"file": "a.py", "line": 2, "quote": "os.system(x)"}],
                       "exploit_path": "p", "suggested_fix": "f"})


def test_tier2_cloud_401_switches_to_next_tier2_model(settings: Settings) -> None:
    provider = Unauthorized({CLOUD})
    provider.script = {"judge:tier1": [_ok("vulnerable", 0.4)],
                       "judge:tier2": [_ok("vulnerable", 0.95)]}
    r = _router(settings, provider)
    assert r.pick("tier2").id == CLOUD  # first in tier 2 until it fails
    out = r.judge(_finding(), LINES)
    assert out.verdict is not None and out.verdict.verdict == "vulnerable"
    assert out.decided_by.startswith("tier2:deepseek-v4-flash")  # next model, same tier
    notes = [d for d in r.degraded if "authentication failed" in d]
    assert len(notes) == 1
    assert CLOUD in notes[0] and "switched to deepseek-v4-flash" in notes[0]
    assert "ollama signin" in notes[0] and "HTTP 401" in notes[0]
    assert r.registry.is_down(r.registry.all["tier2"][0])


def test_failed_model_is_not_retried_for_the_rest_of_the_run(settings: Settings) -> None:
    provider = Unauthorized({CLOUD}, status=403)
    provider.script = {"judge:tier1": [_ok("vulnerable", 0.4)],  # always escalates to tier 2
                       "judge:tier2": [_ok("vulnerable", 0.95)]}
    r = _router(settings, provider)
    for i in range(3):
        f = _finding()
        f.context_hash = f"c{i}"
        assert r.judge(f, LINES).verdict is not None
    assert provider.attempts[CLOUD] == 1  # one 403, then skipped for the whole run
    assert sum("access forbidden" in d and CLOUD in d for d in r.degraded) == 1


def test_verifier_auth_failure_falls_back_to_another_family(settings: Settings) -> None:
    provider = Unauthorized({"apple-foundationmodel"})
    r = _router(settings, provider)
    judge = r.registry.all["tier2"][1]  # a deepseek-family finder: verifier comes from tier 1
    assert r.pick_verifier(judge).id == "apple-foundationmodel"
    out, _, _, spec = r.ask_fb(lambda: r.pick_verifier(judge), "verify", "sys",
                               "TASK: verify\nCLAIM: vulnerable\nARG: tainted\n",
                               __import__("rce_sentinel.orchestrator.router",
                                          fromlist=["VerifyOut"]).VerifyOut)
    assert spec is not None and spec.id == "qwen2.5:3b" and out is not None
    assert any("apple-foundationmodel" in d and "switched to qwen2.5:3b" in d
               for d in r.degraded)


def test_all_models_failing_degrades_instead_of_crashing(settings: Settings) -> None:
    every = {m.id for t in ModelRegistry(settings.models, "mock").all.values() for m in t}
    r = _router(settings, Unauthorized(every))
    out = r.judge(_finding(), LINES)
    assert out.verdict is None  # rules-only verdict stands
    assert any("authentication failed" in d for d in r.degraded)


def test_non_auth_errors_do_not_mark_models_down(settings: Settings) -> None:
    provider = Unauthorized({CLOUD}, status=500)
    provider.script = {"judge:tier1": [_ok("vulnerable", 0.4)],
                       "judge:tier2": [_ok("vulnerable", 0.95)]}
    r = _router(settings, provider)
    r.judge(_finding(), LINES)
    assert provider.attempts[CLOUD] >= 1
    assert not r.registry.is_down(r.registry.all["tier2"][0])


@pytest.mark.parametrize("status", [401, 402, 403])
def test_message_reaches_the_report(settings: Settings, status: int) -> None:
    import io

    from rce_sentinel.models import ScanReport
    from rce_sentinel.report import terminal

    provider = Unauthorized({CLOUD}, status=status)
    provider.script = {"judge:tier1": [_ok("vulnerable", 0.4)],
                       "judge:tier2": [_ok("vulnerable", 0.95)]}
    r = _router(settings, provider)
    r.judge(_finding(), LINES)
    rep = ScanReport(run_id="x", mode="full", started="t", duration_s=0.1, degraded=r.degraded)
    buf = io.StringIO()
    terminal(rep, buf)
    assert "degraded: model fallback (" in buf.getvalue()
    assert CLOUD in buf.getvalue() and f"HTTP {status}" in buf.getvalue()


def test_plan_limit_402_is_explained_as_a_plan_issue(settings: Settings) -> None:
    provider = Unauthorized({CLOUD}, status=402)
    provider.script = {"judge:tier1": [_ok("vulnerable", 0.4)],
                       "judge:tier2": [_ok("vulnerable", 0.95)]}
    r = _router(settings, provider)
    r.judge(_finding(), LINES)
    note = next(d for d in r.degraded if CLOUD in d)
    assert "not included in your plan" in note and "HTTP 402" in note
    assert "ollama signin" not in note and "upgrade the plan" in note
