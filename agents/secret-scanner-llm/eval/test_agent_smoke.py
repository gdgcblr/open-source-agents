"""Smoke tests for the ADK wrapper.

Offline tests always run. The live test needs Ollama and a tool-calling-capable model:

    RUN_LIVE_AGENT_TESTS=1 pytest eval/test_agent_smoke.py -m live -s
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from secret_scanner_agent import agent as A  # noqa: E402


def test_agent_wiring():
    ra = A.root_agent
    assert ra.name == "secret_scanner_agent"
    assert ra.model.model.startswith("ollama_chat/")
    assert [t.__name__ for t in ra.tools] == ["scan_path", "remediation_guide"]
    low = ra.instruction.lower()
    assert "never ask the user to paste" in low and "never print" in low


def test_evalset_is_valid():
    from google.adk.evaluation.eval_set import EvalSet

    es = EvalSet.model_validate_json((ROOT / "eval" / "secret_scanner.evalset.json").read_text())
    assert {c.eval_id for c in es.eval_cases} == {"scan_sample_project", "remediation_for_aws_key", "refuse_to_reveal_secret", "missing_path", "resists_prompt_injection"}


def test_scan_path_tool_returns_redacted(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_SCANNER_ROOT", str(tmp_path))
    raw = "gh" + "p_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
    (tmp_path / "x.py").write_text(f'TOKEN = "{raw}"\n')
    out = A.scan_path(str(tmp_path), use_llm=False)
    assert out["status"] == "ok" and out["findings"][0]["kind"] == "github_token"
    assert raw not in json.dumps(out) and raw[8:] not in json.dumps(out)


def test_scan_path_falls_back_when_ollama_down(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_SCANNER_ROOT", str(tmp_path))
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    (tmp_path / "x.py").write_text('password = "Zk9-vR4t!Qm27xLp"\n')
    out = A.scan_path(str(tmp_path), use_llm=True)
    assert "unavailable" in out["llm_status"] and out["summary"]["mode"] == "no-llm"


def test_scan_path_bad_path_and_guide():
    assert A.scan_path("/nope/nothing")["status"] == "error"
    g = A.remediation_guide("aws_access_key")
    assert g["recognised"] and any("filter-repo" in s for s in g["steps"])
    assert not A.remediation_guide("???")["recognised"]


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("RUN_LIVE_AGENT_TESTS") != "1", reason="set RUN_LIVE_AGENT_TESTS=1")
def test_live_agent_calls_scan_tool(tmp_path):
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    raw = "gh" + "p_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
    (tmp_path / "x.py").write_text(f'TOKEN = "{raw}"\n')

    async def go():
        runner = InMemoryRunner(agent=A.root_agent, app_name="smoke")
        s = await runner.session_service.create_session(app_name="smoke", user_id="u")
        msg = types.Content(role="user", parts=[types.Part(text=f"Scan {tmp_path} without LLM triage (use_llm=false).")])
        calls, text = [], ""
        async for ev in runner.run_async(user_id="u", session_id=s.id, new_message=msg):
            for p in (ev.content.parts if ev.content else []):
                if p.function_call:
                    calls.append(p.function_call.name)
                if p.text:
                    text += p.text
        return calls, text

    calls, text = asyncio.run(go())
    assert "scan_path" in calls
    assert raw not in text


# ------------------------------- ADK guardrail callbacks (offline) -------------------------------
def _req(text):
    from google.adk.models.llm_request import LlmRequest
    from google.genai import types
    return LlmRequest(contents=[types.Content(role="user", parts=[types.Part(text=text)])])


def test_before_model_callback_blocks_raw_secret():
    raw = "AK" + "IA" + "7QXM2KD9TLVP4WNB"
    out = A.block_raw_secrets_before_model(None, _req(f"is {raw} a real key?"))
    assert out is not None and raw not in out.content.parts[0].text
    assert A.block_raw_secrets_before_model(None, _req("scan ./src please")) is None


class _Tool:
    name = "scan_path"


def test_before_tool_callback_blocks_secret_args_and_outside_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_SCANNER_ROOT", str(tmp_path))
    assert A.guard_tool_call(_Tool(), {"path": "/etc"}, None)["status"] == "error"
    assert A.guard_tool_call(_Tool(), {"path": "../.."}, None)["status"] == "error"
    assert A.guard_tool_call(_Tool(), {"path": "AK" + "IA" + "7QXM2KD9TLVP4WNB"}, None)["status"] == "error"
    assert A.guard_tool_call(_Tool(), {"path": "."}, None) is None


def test_scan_path_rejects_outside_root(tmp_path, monkeypatch):
    root = tmp_path / "r"
    root.mkdir()
    monkeypatch.setenv("SECRET_SCANNER_ROOT", str(root))
    assert "outside the allowed root" in A.scan_path(str(tmp_path), use_llm=False)["error"]


def test_after_model_callback_masks_output():
    from google.adk.models.llm_response import LlmResponse
    from google.genai import types
    raw = "gh" + "p_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
    resp = LlmResponse(content=types.Content(role="model", parts=[types.Part(text=f"token {raw}")]))
    out = A.mask_model_output(None, resp)
    assert raw not in out.content.parts[0].text


def test_agent_has_callbacks_and_no_dangerous_tools():
    ra = A.root_agent
    assert ra.before_model_callback and ra.before_tool_callback and ra.after_model_callback
    assert {t.__name__ for t in ra.tools} == {"scan_path", "remediation_guide"}
