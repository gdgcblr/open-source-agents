"""Regression tests for review round 4: guess guard (tool names, other agents' output, per-session
state, reset_guard recovery), whole-word matching of short values, vault robustness, CLI prompts."""

import json
import threading
import types

import pytest

from d3v_keyguard import cli
from d3v_keyguard.adk import GUESS_NOTICE, REMOVED_NOTICE, KeyguardADK
from d3v_keyguard.errors import TamperDetected
from d3v_keyguard.policy import Policy
from d3v_keyguard.prompt import GuiPrompt, TtyPrompt
from d3v_keyguard.redact import Redactor
from d3v_keyguard.vault import Vault

from test_hardening import _runner, cli_vault  # noqa: F401
from test_keyguard import FAST, PIN, FakeKeyring, FakePrompt, Tool, run, vault  # noqa: F401

PLACEHOLDER = "[REDACTED:keyguard://card_pin]"


def _gt():
    from google.genai import types as gt

    return gt


# ------------------------------------------------------------------ tool names
@pytest.mark.parametrize("plugin_mode", [True, False])
def test_unknown_tool_name_with_candidates_trips_instead_of_confirming(vault, plugin_mode):
    vault.put("card_pin", "4821")
    vault.lock()
    kg = KeyguardADK(vault=vault, policy=Policy(), prompt=FakePrompt([PIN]))
    name = "t_" + "_".join(f"{i:04d}" for i in range(4815, 4826))
    seen, history = _runner(kg, [], [("unlock_vault", {"reason": "status"}), (name, {})], plugin_mode=plugin_mode)
    assert kg.tripped and not vault.is_unlocked()
    assert len(seen) == 2  # no model turn after the guessing call
    assert PLACEHOLDER not in "\n".join(seen) + history and GUESS_NOTICE in history


def test_tool_name_is_checked_in_before_tool_and_in_history(vault):
    vault.put("card_pin", "4821")
    kg = KeyguardADK(vault=vault, policy=Policy(), prompt=FakePrompt())
    kg._learn_active_values()
    assert run(kg.before_tool_callback(Tool("try_4821"), {}, None))["error"] == GUESS_NOTICE
    kg.reset_guard()
    gt = _gt()
    call = gt.Part(function_call=gt.FunctionCall(name="x_4822_4821", args={}))
    req = types.SimpleNamespace(contents=[gt.Content(role="model", parts=[call])], config=None)
    assert kg.before_model_callback(None, req).content.parts[0].text == GUESS_NOTICE


# ------------------------------------------------------- other agents' output
def test_sub_agent_output_re_presented_as_user_content_trips(vault):
    from google.adk.agents import Agent
    from google.adk.apps import App
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse
    from google.adk.runners import InMemoryRunner

    gt = _gt()
    vault.put("card_pin", "4821")
    vault.lock()
    kg = KeyguardADK(vault=vault, policy=Policy(), prompt=FakePrompt([PIN]))
    seen_root = []
    cands = " ".join(f"{i:04d}" for i in range(4800, 4850))

    def reply(*parts):
        return LlmResponse(content=gt.Content(role="model", parts=list(parts)))

    def call(name, **args):
        return gt.Part(function_call=gt.FunctionCall(name=name, args=args))

    class Sub(BaseLlm):
        model: str = "sub"

        async def generate_content_async(self, llm_request, stream=False):
            yield reply(gt.Part(text="candidates: " + cands), call("transfer_to_agent", agent_name="root"))

    class Root(BaseLlm):
        model: str = "root"

        async def generate_content_async(self, llm_request, stream=False):
            seen_root.append(json.dumps([c.model_dump(mode="json") for c in llm_request.contents]))
            n = len(seen_root)
            yield reply(call("unlock_vault", reason="x") if n == 1 else
                        call("transfer_to_agent", agent_name="sub") if n == 2 else gt.Part(text="done"))

    sub = Agent(name="sub", model=Sub(), instruction="x", description="helper")
    root = Agent(name="root", model=Root(), instruction="x", tools=[*kg.tools], sub_agents=[sub])
    runner = InMemoryRunner(app=App(name="demo", root_agent=root, plugins=[kg.plugin()]))

    async def go():
        s = await runner.session_service.create_session(app_name="demo", user_id="u")
        msg = gt.Content(role="user", parts=[gt.Part(text="go")])
        async for _ in runner.run_async(user_id="u", session_id=s.id, new_message=msg):
            pass
        return s.id

    sid = run(go())
    assert kg.is_tripped(sid) and not vault.is_unlocked()
    assert len(seen_root) == 2 and not any(PLACEHOLDER in r for r in seen_root)


def test_agent_tool_result_is_checked_not_redacted(vault):
    from google.adk.agents import Agent
    from google.adk.tools.agent_tool import AgentTool

    vault.put("card_pin", "4821")
    kg = KeyguardADK(vault=vault, policy=Policy(), prompt=FakePrompt())
    kg._learn_active_values()
    tool = AgentTool(agent=Agent(name="helper", model="gemini-2.5-flash"))
    out = run(kg.after_tool_callback(tool, {"request": "x"}, None, "try 4820 4821 4822"))
    assert out["error"] == GUESS_NOTICE and kg.tripped
    kg.reset_guard()
    other = run(kg.after_tool_callback(Tool("web_fetch"), {}, None, "page: 4820 4821 4822"))
    assert PLACEHOLDER in other["result"]  # third-party content: scrubbed (documented limitation)


# ------------------------------------------------- per-session state, recovery
def _chat_runner(kg, replies):
    """Runner whose model answers each request with replies[n] (text); returns (send, requests)."""
    from google.adk.agents import Agent
    from google.adk.apps import App
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse
    from google.adk.runners import InMemoryRunner

    gt = _gt()
    requests = []

    class Model(BaseLlm):
        model: str = "scripted"

        async def generate_content_async(self, llm_request, stream=False):
            requests.append(json.dumps([c.model_dump(mode="json") for c in llm_request.contents]))
            text = replies[min(len(requests) - 1, len(replies) - 1)]
            yield LlmResponse(content=gt.Content(role="model", parts=[gt.Part(text=text)]))

    runner = InMemoryRunner(app=App(name="t", root_agent=Agent(name="a", model=Model(), tools=[*kg.tools]),
                                    plugins=[kg.plugin()]))

    async def new_session():
        return (await runner.session_service.create_session(app_name="t", user_id="u")).id

    async def send(sid, text):
        out = []
        msg = gt.Content(role="user", parts=[gt.Part(text=text)])
        async for ev in runner.run_async(user_id="u", session_id=sid, new_message=msg):
            out += [p.text for p in (ev.content.parts if ev.content else []) if p.text]
        return " ".join(out)

    return (lambda: run(new_session())), (lambda sid, text: run(send(sid, text))), requests


def test_reset_guard_recovers_the_session_and_trips_are_per_session(vault):
    vault.put("db_user", "admin-7")
    kg = KeyguardADK(vault=vault, policy=Policy(), prompt=FakePrompt())
    kg._learn_active_values()
    new_session, send, requests = _chat_runner(kg, ["log in as admin-7 please", "ok", "ok", "ok"])
    a, b = new_session(), new_session()
    assert send(a, "hi") == "log in as admin-7 please"  # final text: no further model call this turn
    assert send(a, "next") == GUESS_NOTICE  # the history is checked on the next request
    assert kg.is_tripped(a) and not kg.is_tripped(b) and not vault.is_unlocked()
    n = len(requests)
    assert send(b, "hello") == "ok" and len(requests) == n + 1  # another session is not blocked
    kg.reset_guard(a)  # a human reviewed session a
    assert send(a, "again") == "ok" and not kg.is_tripped(a)
    last = requests[-1]
    assert REMOVED_NOTICE in last and "admin-7" not in last and "REDACTED" not in last
    assert send(a, "and again") == "ok" and not kg.is_tripped(a)  # does not re-trip


def test_short_values_match_whole_words_only():
    r = Redactor()
    r.add("db_user", "admin")
    assert not r.contains("sign in as an administrator")
    assert r.scrub_text("administrator") == "administrator"
    assert r.contains("user: admin.") and r.scrub_text("user=admin;") == "user=[REDACTED:keyguard://db_user];"
    r.add("pw", "hunter2!")  # short raw value: its encoded forms still match anywhere
    import base64

    assert "[REDACTED:keyguard://pw]" in r.scrub_text(base64.b64encode(b"alice:hunter2!").decode())


# ---------------------------------------------------------------- vault robustness
def test_invalid_utf8_vault_is_tamper_detected(vault):
    vault.path.write_bytes(b'{"format": "\xff\xfe"}')
    for op in (vault.status, vault.list):
        with pytest.raises(TamperDetected):
            op()


def test_huge_timeouts_do_not_overflow_the_timer(tmp_path):
    v = Vault(tmp_path / "v.json", keyring_backend=FakeKeyring(), kdf_params=FAST, idle_timeout=1e12,
              max_session=1e12)
    v.create(PIN)
    assert v._timer.interval < threading.TIMEOUT_MAX and v.is_unlocked()


def test_older_vault_restored_after_reinit_is_refused(tmp_path):
    kr, path = FakeKeyring(), tmp_path / "v.json"
    v = Vault(path, keyring_backend=kr, kdf_params=FAST)
    v.create(PIN)
    v.put("old", "old-secret-value-1")
    old = path.read_bytes()
    v.lock()
    path.unlink()
    Vault(path, keyring_backend=kr, kdf_params=FAST).create("other-pass-1")
    path.write_bytes(old)
    with pytest.raises(TamperDetected, match="re-init"):
        Vault(path, keyring_backend=kr, kdf_params=FAST).status()


def test_reunlock_wipes_previous_keys_and_status_reports_verification(vault):
    old = vault._priv
    vault.unlock(PIN)
    assert old is not vault._priv and not any(old)
    assert vault.status()["verified"] is True
    vault.lock()
    assert vault.status()["verified"] is False


# ------------------------------------------------------------------------ CLI
def test_cli_honours_keyguard_prompt_even_with_a_tty(monkeypatch):
    monkeypatch.setattr(cli, "_tty", lambda: True)
    monkeypatch.setenv("KEYGUARD_PROMPT", "gui")
    assert isinstance(cli._prompt(), GuiPrompt)
    monkeypatch.setenv("KEYGUARD_PROMPT", "tty")
    assert isinstance(cli._prompt(), TtyPrompt)


def test_reveal_warns_and_needs_the_typed_name(cli_vault, monkeypatch, capfd):
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    cli_vault.prompt.answers = ["something-else", PIN]
    assert cli.main(["reveal", "gh"]) == 130
    assert "ghp_cli" not in capfd.readouterr().out
    assert "PRINT the plaintext" in cli_vault.prompt.asked[-1]
    cli_vault.prompt.answers = ["gh", PIN]
    assert cli.main(["reveal", "gh"]) == 0
    assert "ghp_cli0123456789abcdefXYZ" in capfd.readouterr().out
    assert all("PRINT the plaintext" in m for m in cli_vault.prompt.asked[-2:])
