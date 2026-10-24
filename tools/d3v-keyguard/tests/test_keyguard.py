import asyncio
import json
import os
import threading
import time
import types

import pytest

from d3v_keyguard import vault as vault_mod
from d3v_keyguard.adk import KeyguardADK
from d3v_keyguard.crypto import KdfParams
from d3v_keyguard.errors import (
    LockedOut,
    PromptCancelled,
    PromptUnavailable,
    SecretExists,
    SecretPending,
    TamperDetected,
    VaultIOError,
    VaultLocked,
    WeakPin,
    WrongPin,
)
from d3v_keyguard.policy import Policy
from d3v_keyguard.prompt import AutoPrompt, review_pending
from d3v_keyguard.redact import Redactor, SecretValue, mask
from d3v_keyguard.vault import Vault

FAST = KdfParams(iterations=1, lanes=1, memory_cost=8)
PIN = "correct-horse"
SECRET = "sk-live-1234567890abcdef"


class FakeKeyring:
    def __init__(self):
        self.store = {}

    def get_password(self, service, user):
        return self.store.get((service, user))

    def set_password(self, service, user, pw):
        self.store[(service, user)] = pw

    def delete_password(self, service, user):
        self.store.pop((service, user), None)


class FakePrompt:
    def __init__(self, answers=None, confirm=True, decision="approve", delay=0.0):
        self.answers = list(answers or [])
        self.asked = []
        self.reviewed = []
        self._confirm = confirm
        self.decision = decision
        self.delay = delay

    def ask_secret(self, title, message):
        self.asked.append(message)
        if self.delay:
            time.sleep(self.delay)
        if not self.answers:
            raise PromptCancelled("cancelled")
        return self.answers.pop(0)

    def confirm(self, title, message):
        return self._confirm

    def review(self, title, message, items):
        self.reviewed.append(items)
        return {i["name"]: self.decision for i in items}


@pytest.fixture
def vault(tmp_path):
    v = Vault(tmp_path / "vault.json", keyring_backend=FakeKeyring(), kdf_params=FAST)
    v.create(PIN)
    return v


def edit(vault, fn):
    data = json.loads(vault.path.read_text())
    fn(data)
    vault.path.write_text(json.dumps(data))


def approve_all(vault):
    return vault.approve({i["name"]: i["digest"] for i in vault.review_items()})


# ------------------------------------------------------------------ vault basics
def test_store_locked_is_pending_then_approved(vault):
    vault.lock()
    assert vault.put("api", SECRET) == "pending"
    with pytest.raises(VaultLocked):
        vault.get("api")
    assert vault.unlock(PIN) == ["api"]
    with pytest.raises(SecretPending):
        vault.get("api")
    assert approve_all(vault) == ["api"]
    assert vault.get("api").reveal() == SECRET


def test_store_unlocked_is_active_and_plaintext_not_on_disk(vault):
    assert vault.put("api", SECRET) == "active"
    assert SECRET not in vault.path.read_text()
    assert vault.get("api").reveal() == SECRET


@pytest.mark.parametrize("weak", ["12345", "123456", "654321", "00000000", "12345678901234567890", "password",
                                  "password1", "aaaaaaaa", "abcdefg", "qwerty"])
def test_weak_passphrases_rejected(tmp_path, weak):
    with pytest.raises(WeakPin):
        Vault(tmp_path / "v.json", keyring_backend=FakeKeyring(), kdf_params=FAST).create(weak)


@pytest.mark.parametrize("pin", ["482913", "70925314", "s3cret", "blue-harbor", "zebra 42 lamp"])
def test_documented_passphrase_rule_accepted(tmp_path, pin):
    # README/CLI: 6+ characters, numeric PINs allowed; only trivial values are rejected.
    Vault(tmp_path / "v.json", keyring_backend=FakeKeyring(), kdf_params=FAST).create(pin)


def test_wrong_pin_backoff_and_lockout(vault):
    vault.lock()
    for _ in range(3):
        with pytest.raises(WrongPin):
            vault.unlock("wrong-pin-1")
    with pytest.raises(LockedOut):
        vault.unlock(PIN)
    assert vault.status()["retry_after"] > 0
    vault.unlock(PIN, human_reset=True)
    assert vault.is_unlocked() and vault.status()["failed_attempts"] == 0


def test_counter_edits_are_detected_not_obeyed(vault):
    vault.lock()
    for _ in range(3):
        with pytest.raises(WrongPin):
            vault.unlock("wrong-pin-1")
    edit(vault, lambda d: d["counters"].update(failed_attempts=0))  # attacker resets the counter
    with pytest.raises(TamperDetected):
        vault.unlock("guess-1234")


def test_unlock_refused_if_attempt_cannot_be_recorded(vault, monkeypatch):
    vault.lock()

    def fail(*a, **k):
        raise VaultIOError("disk busy")

    monkeypatch.setattr(vault, "_save", fail)
    with pytest.raises(VaultIOError):
        vault.unlock(PIN)
    assert not vault.is_unlocked()


def test_rollback_and_entry_deletion_detected(vault):
    vault.put("tok", "VALUE-ONE-xxxxxxx")
    old = vault.path.read_text()
    vault.put("tok", "VALUE-TWO-yyyyyyy", overwrite=True)
    vault.path.write_text(old)  # restore an older (validly MAC'd) copy
    with pytest.raises(TamperDetected, match="rollback"):
        vault.get("tok")
    vault.path.write_text(old)
    edit(vault, lambda d: d["entries"].pop("tok"))
    with pytest.raises(TamperDetected):
        vault.list()


def test_public_key_substitution_detected(vault, tmp_path):
    other = Vault(tmp_path / "other.json", keyring_backend=FakeKeyring(), kdf_params=FAST)
    other.create(PIN)
    edit(vault, lambda d: d.update(public_key=json.loads(other.path.read_text())["public_key"]))
    with pytest.raises(TamperDetected):
        vault.put("x", SECRET)


def test_planted_entry_and_swapped_ciphertext_rejected(vault):
    vault.put("a", SECRET)
    vault.put("b", "another-secret-value-xyz")
    edit(vault, lambda d: d["entries"]["a"].update(box=d["entries"]["b"]["box"]))
    with pytest.raises(TamperDetected):
        vault.get("a")


@pytest.mark.parametrize("content", ["", '{"format": "d3v-keyguard/2", "vault_id": ', "[]", "null"])
def test_corrupt_vault_raises_tamper_detected(vault, content):
    vault.path.write_text(content)
    for op in (vault.status, vault.list, lambda: vault.put("x", SECRET)):
        with pytest.raises(TamperDetected):
            op()


def test_garbage_entry_with_valid_mac_is_tamper_not_crash(vault):
    # Even an attacker who has the pepper (and so can re-MAC) only causes TamperDetected.
    data = json.loads(vault.path.read_text())
    data["entries"]["evil"] = "not-a-dict"
    pepper = vault._pepper(data["vault_id"])
    vault._save(data, pepper)
    with pytest.raises(TamperDetected):
        vault.list()


def test_kdf_downgrade_rejected(tmp_path):
    kr = FakeKeyring()
    weak = Vault(tmp_path / "v.json", keyring_backend=kr, kdf_params=FAST)
    weak.create(PIN)
    with pytest.raises(TamperDetected):
        Vault(tmp_path / "v.json", keyring_backend=kr).status()


def test_change_pin_rotates_keys_and_revokes_old_copies(vault):
    vault.put("api", SECRET)
    old_file = vault.path.read_text()
    vault.change_pin(PIN, "new-pin-123")
    vault.put("newsecret", "AFTER-CHANGE-zzzzzzz")
    vault.lock()
    with pytest.raises(WrongPin):
        vault.unlock(PIN)
    vault.unlock("new-pin-123", human_reset=True)
    assert vault.get("api").reveal() == SECRET
    # Attack: old header + current entries, unlocked with the old PIN.
    current = json.loads(vault.path.read_text())
    forged = json.loads(old_file)
    forged["entries"] = current["entries"]
    forged["generation"] = current["generation"] + 1
    vault.lock()
    vault.path.write_text(json.dumps(forged))
    with pytest.raises(TamperDetected):
        vault.unlock(PIN)


def test_idle_timeout_locks(tmp_path):
    now = [0.0]
    v = Vault(tmp_path / "v.json", keyring_backend=FakeKeyring(), kdf_params=FAST,
              idle_timeout=10, clock=lambda: now[0])
    v.create(PIN)
    assert v.is_unlocked()
    now[0] = 11
    assert not v.is_unlocked()


def test_auto_lock_timer_wipes_keys_without_access(tmp_path):
    v = Vault(tmp_path / "v.json", keyring_backend=FakeKeyring(), kdf_params=FAST, idle_timeout=0.2)
    v.create(PIN)
    time.sleep(1.2)
    assert v._priv is None


def test_bad_timeouts_fall_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("KEYGUARD_IDLE_TIMEOUT", "inf")
    v = Vault(tmp_path / "v.json", keyring_backend=FakeKeyring(), max_session=float("nan"))
    assert v.idle_timeout == 300 and v.max_session == 3600


# ------------------------------------------------------- pending / approval
def test_locked_put_cannot_silently_replace_active_secret(vault):
    vault.put("github_token", SECRET)
    vault.lock()
    with pytest.raises(SecretExists):
        vault.put("github_token", "attacker-value-0000")
    assert vault.put("github_token", "attacker-value-0000", overwrite=True) == "pending"
    vault.unlock(PIN)
    assert vault.get("github_token").reveal() == SECRET  # old value still active
    (item,) = vault.review_items()
    assert item["replaces"] and item["preview"] == mask("attacker-value-0000")
    assert vault.reject(["github_token"]) == ["github_token"]
    assert vault.get("github_token").reveal() == SECRET


def test_approval_is_bound_to_reviewed_content(vault):
    vault.lock()
    vault.put("planted", "ORIGINAL-value-1234")
    vault.unlock(PIN)
    reviewed = {i["name"]: i["digest"] for i in vault.review_items()}
    vault.lock()
    vault.put("planted", "SWAPPED-by-attacker-2")  # swapped while the dialog is open
    vault.unlock(PIN)
    assert vault.approve(reviewed) == []
    with pytest.raises(SecretPending):
        vault.get("planted")


def test_review_pending_per_entry_decisions(vault):
    vault.lock()
    vault.put("mine", "my-own-value-123", {"description": "mine"})
    vault.put("planted", "planted-value-456", captured_from="web_fetch")
    vault.put("forged", "forged-value-7890", {"captured_from": "login"})  # reserved key: dropped
    vault.unlock(PIN)
    assert next(i for i in vault.review_items() if i["name"] == "forged")["metadata"] == {}

    class Picky(FakePrompt):
        def review(self, title, message, items):
            assert any("captured from tool 'web_fetch' (unverified)" in i["label"] for i in items)
            assert not any("login" in i["label"] for i in items)
            return {"mine": "approve", "planted": "reject", "forged": "reject"}

    result = review_pending(vault, Picky())
    assert result == {"approved": ["mine"], "rejected": ["forged", "planted"], "pending": []}
    assert [i["name"] for i in vault.list()] == ["mine"]


# ----------------------------------------------------------- concurrency / IO
def test_concurrent_writers_with_file_lock(tmp_path):
    kr = FakeKeyring()
    path = tmp_path / "v.json"
    Vault(path, keyring_backend=kr, kdf_params=FAST).create(PIN)
    errors = []

    def writer(i):
        v = Vault(path, keyring_backend=kr, kdf_params=FAST)
        for j in range(5):
            try:
                v.put(f"s{i}_{j}", f"value-{i}-{j}-xxxx")
            except Exception as exc:  # pragma: no cover - reported below
                errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(Vault(path, keyring_backend=kr, kdf_params=FAST).list()) == 20


@pytest.mark.skipif(os.name != "nt", reason="Windows sharing semantics")
def test_write_retries_while_another_reader_holds_file(vault):
    handle = open(vault.path, "rb")
    threading.Timer(0.3, handle.close).start()
    assert vault.put("x", SECRET) == "active"


def test_busy_vault_gives_clean_error(vault, monkeypatch):
    monkeypatch.setattr(vault_mod, "LOCK_TIMEOUT", 0.2)
    other = Vault(vault.path, keyring_backend=vault._backend, kdf_params=FAST)
    with vault_mod._file_lock(vault.path.with_name("vault.json.lock")):
        with pytest.raises(VaultIOError):
            other.list()


# ------------------------------------------------------------------ redaction
def test_secret_value_masked():
    s = SecretValue("api", SECRET)
    assert SECRET not in repr(s) and SECRET not in str(s) and SECRET not in f"{s}"
    assert mask("short") == "****[5 chars]"


def test_redactor_encoded_variants():
    import base64

    r = Redactor()
    r.add("pw", "hunter2-Secret!")
    for leaked in ("hunter2-Secret!".encode().hex(), base64.b64encode(b"alice:hunter2-Secret!").decode(),
                   base64.b64encode(b"bob:hunter2-Secret!").decode(), base64.b64encode(b"carl:hunter2-Secret!").decode(),
                   json.dumps({"p": "hunter2-Secret!"}), "hunter2-Secret%21"):
        assert "[REDACTED:keyguard://pw]" in r.scrub_text(leaked), leaked


# -------------------------------------------------------------------- prompts
def test_gui_cancel_does_not_fall_back_to_terminal(monkeypatch):
    from d3v_keyguard import prompt as prompt_mod

    p = AutoPrompt()
    used_tty = []
    monkeypatch.setattr(prompt_mod, "_tty", lambda: True)
    monkeypatch.setattr(p._tty, "ask_secret", lambda *a: used_tty.append(1) or "x")
    monkeypatch.setattr(p._gui, "_run", lambda req: (_ for _ in ()).throw(PromptCancelled("cancelled")))
    with pytest.raises(PromptCancelled):
        p.ask_secret("t", "m")
    assert not used_tty
    monkeypatch.setattr(p._gui, "_run", lambda req: (_ for _ in ()).throw(PromptUnavailable("no tk")))
    assert p.ask_secret("t", "m") == "x" and used_tty


# ------------------------------------------------------------------------ ADK
class Tool:
    """Minimal ADK-like tool: records the args it was actually called with."""

    def __init__(self, name, fn=None):
        self.name = name
        self.fn = fn or (lambda **kw: {"echo": json.dumps(kw)})
        self.calls = []

    async def run_async(self, *, args, tool_context):
        self.calls.append(args)
        return self.fn(**args)


def run(coro):
    return asyncio.run(coro)


def test_adk_injection_keeps_adk_args_clean_and_scrubs(vault):
    vault.put("demo_api", SECRET)
    vault.lock()
    kg = KeyguardADK(vault=vault, policy=Policy({"call_api": ["demo_*"]}), prompt=FakePrompt([PIN]))
    tool = Tool("call_api", lambda url, headers: f"sent {headers['Authorization']} to {url}")
    args = {"url": "https://x", "headers": {"Authorization": "Bearer keyguard://demo_api"}}
    out = run(kg.before_tool_callback(tool, args, None))
    assert tool.calls[0]["headers"]["Authorization"] == f"Bearer {SECRET}"  # the tool got the value
    assert args["headers"]["Authorization"] == "Bearer keyguard://demo_api"  # ADK's dict did not
    assert SECRET not in json.dumps(out) and "[REDACTED:keyguard://demo_api]" in out["result"]
    assert "Arguments:" in kg.prompt.asked[0] and "https://x" in kg.prompt.asked[0]

    denied = run(kg.before_tool_callback(Tool("web_fetch"), {"q": "keyguard://demo_api"}, None))
    assert denied["status"] == "error" and SECRET not in json.dumps(denied)


def test_adk_non_dict_results_scrubbed_even_after_lock(vault):
    vault.put("demo_api", SECRET)
    kg = KeyguardADK(vault=vault, policy=Policy({"call_api": ["demo_*"]}), prompt=FakePrompt())
    run(kg.before_tool_callback(Tool("call_api", lambda authorization: "ok"), {"authorization": "keyguard://demo_api"},
                                None))
    tools = {t.__name__: t for t in kg.tools}
    run(tools["lock_vault"]())  # e.g. a prompt-injected model, or idle auto-lock
    for result in (f"debug log: {SECRET}", [f"x {SECRET}"], (SECRET,)):
        out = run(kg.after_tool_callback(Tool("read_debug_log"), {}, None, result))
        assert SECRET not in json.dumps(out) and isinstance(out, dict)

    from google.genai import types as gt

    req = types.SimpleNamespace(contents=[gt.Content(role="user", parts=[gt.Part(text=f"leak {SECRET}")])],
                                config=gt.GenerateContentConfig(system_instruction=f"sys {SECRET}"))
    kg.before_model_callback(None, req)
    assert SECRET not in req.contents[0].parts[0].text and SECRET not in req.config.system_instruction


def test_adk_tool_exception_is_scrubbed(vault):
    vault.put("demo_api", SECRET)

    def boom(authorization):
        raise ValueError(f"Invalid header value {authorization!r}")

    kg = KeyguardADK(vault=vault, policy=Policy({"call_api": ["demo_*"]}), prompt=FakePrompt())
    out = run(kg.before_tool_callback(Tool("call_api", boom), {"authorization": "keyguard://demo_api"}, None))
    assert out["status"] == "error" and SECRET not in json.dumps(out)
    err = run(kg.on_tool_error_callback(Tool("other"), {}, None, RuntimeError(f"bad {SECRET}")))
    assert SECRET not in json.dumps(err)


def test_adk_capture_and_tools_never_return_plaintext(vault):
    kg = KeyguardADK(vault=vault, policy=Policy(), capture={"login": {"session_token": "sess"}},
                     prompt=FakePrompt([SECRET]))
    out = run(kg.after_tool_callback(Tool("login"), {}, None, {"session_token": "tok-abcdefghijklmnop"}))
    assert out["session_token"] == "keyguard://sess"
    tools = {t.__name__: t for t in kg.tools}
    stored = run(tools["store_secret"]("gh", "github token"))
    assert stored["status"] == "success"
    for result in (run(tools["list_secrets"]()), run(tools["describe_secret"]("gh")), run(tools["vault_status"]())):
        dumped = json.dumps(result)
        assert SECRET not in dumped and "tok-abcdefghijklmnop" not in dumped
    assert run(tools["describe_secret"]("gh"))["metadata"] == {"description": "github token"}
    assert run(kg.before_tool_callback(Tool("store_secret"), {"name": "x", "value": "leaky-value"}, None))[
        "status"] == "error"
    assert "already exists" in run(tools["store_secret"]("gh"))["error"]


def test_adk_tools_return_errors_on_corrupt_vault(vault):
    vault.path.write_text('{"truncated":')
    kg = KeyguardADK(vault=vault, policy=Policy({"t": ["*"]}), prompt=FakePrompt())
    tools = {t.__name__: t for t in kg.tools}
    assert run(tools["vault_status"]())["status"] == "error"
    assert run(tools["list_secrets"]())["status"] == "error"
    vault.lock()
    assert run(kg.before_tool_callback(Tool("t"), {"a": "keyguard://x"}, None))["status"] == "error"


def test_adk_prompt_does_not_block_event_loop(vault):
    vault.put("demo_api", SECRET)
    vault.lock()
    kg = KeyguardADK(vault=vault, policy=Policy({"t": ["*"]}), prompt=FakePrompt([PIN], delay=0.5))

    async def main():
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.05)
                ticks += 1

        task = asyncio.create_task(ticker())
        await kg.before_tool_callback(Tool("t", lambda a: "ok"), {"a": "keyguard://demo_api"}, None)
        task.cancel()
        return ticks

    assert run(main()) >= 5


def test_adk_function_tools_build():
    from google.adk.tools import FunctionTool

    kg = KeyguardADK(vault=Vault("unused.json", keyring_backend=FakeKeyring()), policy=Policy(),
                     prompt=FakePrompt())
    for fn in kg.tools:
        assert FunctionTool(fn)._get_declaration().name == fn.__name__


def test_adk_runner_plugin_and_observers_never_see_plaintext(vault):
    """Full InMemoryRunner with kg.plugin() first and a logging-style plugin after it."""
    from google.adk.agents import Agent
    from google.adk.apps import App
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse
    from google.adk.plugins.base_plugin import BasePlugin
    from google.adk.runners import InMemoryRunner
    from google.genai import types as gt

    vault.put("demo_api", SECRET)
    seen = []

    class Observer(BasePlugin):
        async def before_tool_callback(self, *, tool, tool_args, tool_context):
            seen.append(json.dumps(tool_args))

        async def after_tool_callback(self, *, tool, tool_args, tool_context, result):
            seen.append(json.dumps(tool_args) + json.dumps(result, default=str))

    script = [("call_api", {"authorization": "keyguard://demo_api"}), ("login", {})]

    class Model(BaseLlm):
        model: str = "scripted"

        async def generate_content_async(self, llm_request, stream=False):
            seen.append(json.dumps([c.model_dump(mode="json") for c in llm_request.contents]))
            turn = sum(1 for c in llm_request.contents for p in (c.parts or []) if p.function_response)
            part = (gt.Part(function_call=gt.FunctionCall(name=script[turn][0], args=script[turn][1]))
                    if turn < len(script) else gt.Part(text="done"))
            yield LlmResponse(content=gt.Content(role="model", parts=[part]))

    def call_api(authorization: str) -> str:
        """Echo."""
        return f"sent {authorization}"

    def login() -> dict:
        """Login."""
        return {"session_token": "sess-0123456789abcdef"}

    kg = KeyguardADK(vault=vault, policy=Policy({"call_api": ["demo_*"]}),
                     capture={"login": {"session_token": "sess"}}, prompt=FakePrompt())
    agent = Agent(name="a", model=Model(), tools=[call_api, login])
    app = App(name="t", root_agent=agent, plugins=[kg.plugin(), Observer(name="observer")])
    runner = InMemoryRunner(app=app)

    async def go():
        s = await runner.session_service.create_session(app_name="t", user_id="u")
        msg = gt.Content(role="user", parts=[gt.Part(text="hi")])
        async for _ in runner.run_async(user_id="u", session_id=s.id, new_message=msg):
            pass
        stored = await runner.session_service.get_session(app_name="t", user_id="u", session_id=s.id)
        return json.dumps([e.model_dump(mode="json") for e in stored.events])

    history = run(go())
    blob = "\n".join(seen) + history
    assert SECRET not in blob and "sess-0123456789abcdef" not in blob
    assert "[REDACTED:keyguard://demo_api]" in history
