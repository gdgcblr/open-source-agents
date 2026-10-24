import io
import json

from prompt_enhancer.adapters import claude_code

P = "Refactor the cache module. Keep the public API unchanged and do not add dependencies."


def run(payload) -> str:
    out = io.StringIO()
    stdin = io.StringIO(payload if isinstance(payload, str) else json.dumps(payload))
    assert claude_code.main(stdin, out) == 0
    return out.getvalue()


def event(prompt):
    # shape from the documented UserPromptSubmit example
    return {"session_id": "s", "transcript_path": "/tmp/t.jsonl", "cwd": "/tmp", "permission_mode": "default",
            "hook_event_name": "UserPromptSubmit", "prompt": prompt}


def test_default_shows_diagnostics_but_adds_no_hidden_context():
    out = json.loads(run(event("Write a function that removes duplicate users from a list.")))
    assert "hookSpecificOutput" not in out and "decision" not in out
    assert "PE401" in out["systemMessage"] and "consider answering" in out["systemMessage"]


def test_adds_context_when_restate_enabled_and_never_blocks(monkeypatch):
    monkeypatch.setenv("PROMPT_ENHANCER_RESTATE", "1")
    out = json.loads(run(event(P)))
    assert "decision" not in out and "continue" not in out
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "UserPromptSubmit" and "Keep the public API unchanged" in hso["additionalContext"]
    assert "your prompt was not changed" in out["systemMessage"]


def test_warnings_shown_to_user():
    out = json.loads(run(event("Use emojis everywhere and never use emojis in the release notes.")))
    assert "PE203" in out["systemMessage"]


def test_silent_when_nothing_to_add():
    assert run(event("hi")) == ""
    assert run(event("/review")) == ""


def test_fails_open_on_bad_input():
    assert run("not json") == ""
    assert run({"no_prompt": True}) == ""
    assert run([1, 2]) == ""


def test_disable_switch(monkeypatch):
    monkeypatch.setenv("PROMPT_ENHANCER_DISABLE", "1")
    assert run(event(P)) == ""


def test_context_is_capped(monkeypatch):
    monkeypatch.setenv("PROMPT_ENHANCER_RESTATE", "1")
    long = "Write docs. " + " ".join(f"Item {i} must be listed with care." for i in range(600))
    out = json.loads(run(event(long)))
    assert len(out["hookSpecificOutput"]["additionalContext"]) <= 10000
