"""Exercise the ADK agent's tools and wiring without calling Gemini."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from slop_detector import agent
from slop_detector.heuristics import run_heuristics
from slop_detector.models import ChangedFile, LlmVerdict, PullRequest

FIXTURE = Path(__file__).parent / "fixtures" / "slop_pr.json"


def ctx():
    pr = PullRequest.model_validate_json(FIXTURE.read_text())
    return SimpleNamespace(state={"pr": pr.model_dump(mode="json"), "heuristics": run_heuristics(pr).model_dump(mode="json")})


def test_overview_includes_heuristics_and_files():
    out = agent.get_pr_overview(ctx())
    assert out["number"] == 101
    assert out["totals"]["files"] == 4
    assert any(s["id"] == "assistant-leakage" for s in out["heuristic_signals"])


def test_overview_without_pr_asks_to_load():
    assert agent.get_pr_overview(SimpleNamespace(state={}))["status"] == "no_pr_loaded"


def test_get_file_diff():
    c = ctx()
    assert "fastjsonschema" in agent.get_file_diff("user_service/api.py", c)["patch"]
    assert "error" in agent.get_file_diff("nope.py", c)


def test_agent_is_wired_for_structured_output(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    investigator, writer = agent.build_agent("gemini-test-model").sub_agents
    assert investigator.model == writer.model == "gemini-test-model"
    assert {t.__name__ for t in investigator.tools} == {"get_pr_overview", "get_file_diff", "load_pull_request"}
    assert investigator.output_key == "analysis" and "at most 8 files" in investigator.instruction
    # The verdict step has no tools, so the server can enforce the JSON schema.
    assert writer.output_schema is LlmVerdict and not writer.tools
    assert "{analysis}" in writer.instruction


def test_ollama_is_default_and_uses_gemma(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("MODEL_NAME", raising=False)
    investigator, _ = agent.build_agent().sub_agents
    assert investigator.model.model == "ollama_chat/gemma4:e2b-it-qat"
    assert "at most 4 files" in investigator.instruction


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "nope")
    with pytest.raises(ValueError):
        agent.build_agent()


def test_parse_verdict_tolerates_fences_and_preamble():
    text = 'Here is my review:\n```json\n{"slop_score": 70, "verdict": "likely_slop", "summary": "s"}\n```'
    v = agent.parse_verdict(text)
    assert v.slop_score == 70 and v.verdict.value == "likely_slop"


def test_lockfiles_and_missing_patches_are_not_evidence():
    pr = PullRequest(files=[
        ChangedFile(filename="uv.lock", additions=900, patch=None),
        ChangedFile(filename="src/big.py", additions=5000, patch=None),
        ChangedFile(filename="src/app.py", additions=1, patch="@@ -1 +1 @@\n+x = 1"),
    ])
    c = SimpleNamespace(state={"pr": pr.model_dump(mode="json"), "heuristics": run_heuristics(pr).model_dump(mode="json")})
    overview = agent.get_pr_overview(c)
    assert [f["filename"] for f in overview["files"]] == ["src/big.py", "src/app.py"]
    assert overview["generated_files_hidden"] == ["uv.lock"]
    assert "NOT evidence" in agent.get_file_diff("src/big.py", c)["note"]
    assert "skip" in agent.get_file_diff("uv.lock", c)["note"]
