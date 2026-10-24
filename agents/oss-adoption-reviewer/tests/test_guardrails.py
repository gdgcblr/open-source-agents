import json
import subprocess
from pathlib import Path

import pytest

from reviewer.guardrails import (after_model_callback, after_tool_callback, before_tool_callback, parse_github_url, redact,
                                 safe_path)
from reviewer.repo_mcp import clone_repo, read_file, scan_repo

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def sandbox(monkeypatch):
    monkeypatch.setenv("REVIEW_ROOT", str(FIXTURES))


def test_traversal_blocked():
    for bad in ["../../etc/passwd", "/etc/passwd", "good_repo/../../../etc/passwd"]:
        with pytest.raises(PermissionError):
            safe_path(bad)
        with pytest.raises(PermissionError):
            read_file(bad)
    with pytest.raises(PermissionError):
        scan_repo("..")


def test_env_file_read_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("REVIEW_ROOT", str(tmp_path))
    (tmp_path / ".env").write_text("KEY=secret")
    (tmp_path / ".env.example").write_text("KEY=changeme")
    (tmp_path / "server.pem").write_text("x")
    (tmp_path / "id_rsa").write_text("x")
    for name in [".env", ".env.local", "server.pem", "id_rsa"]:
        (tmp_path / name).touch()
        with pytest.raises(PermissionError):
            read_file(name)
    assert "changeme" in read_file(".env.example")


def test_symlink_escape_blocked(tmp_path, monkeypatch):
    secret = tmp_path / "outside.txt"
    secret.write_text("top secret")
    root = tmp_path / "root"
    root.mkdir()
    (root / "link.txt").symlink_to(secret)
    (root / "linkdir").symlink_to(tmp_path)
    monkeypatch.setenv("REVIEW_ROOT", str(root))
    with pytest.raises(PermissionError):
        read_file("link.txt")
    with pytest.raises(PermissionError):
        scan_repo("linkdir")


def test_read_file_wraps_untrusted_and_redacts():
    out = read_file("injected_repo/README.md")
    assert "<untrusted_file" in out and "</untrusted_file>" in out
    assert redact("key sk-abcdefghijklmnopqrstuv and ghp_" + "a" * 36) == "key [REDACTED] and [REDACTED]"
    assert redact("gemini AQ." + "Ab8_x-" * 8) == "gemini [REDACTED]"


def test_max_bytes_is_capped():
    assert len(read_file("good_repo/README.md", max_bytes=10)) < len(read_file("good_repo/README.md", max_bytes=200))
    assert "Goodapp" in read_file("good_repo/README.md", max_bytes=10) and "Prerequisites" not in read_file(
        "good_repo/README.md", max_bytes=10)


class Tool:
    def __init__(self, name):
        self.name = name


def test_before_tool_callback_blocks_escape_and_secrets():
    assert "error" in before_tool_callback(Tool("scan_repo"), {"path": "../.."}, None)
    assert "error" in before_tool_callback(Tool("read_file"), {"path": "x/.env"}, None)
    assert before_tool_callback(Tool("scan_repo"), {"path": "good_repo"}, None) is None


def _resp(text):
    from google.adk.models.llm_response import LlmResponse
    from google.genai import types
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))


DIMS = ["Usefulness & clarity", "Ease of adoption", "Maintainability & contributor friction",
        "Distribution & scale", "Friction red flags"]


class Ctx:
    def __init__(self, state=None):
        self.state = state or {}


def test_after_model_callback_warns_and_redacts():
    out = after_model_callback(None, _resp("## Top 5 fixes\nAll good. key sk-abcdefghijklmnopqrstuv"))
    text = out.content.parts[0].text
    assert "[REDACTED]" in text and "Output check failed" in text
    full = "\n".join(f"## {d} — 3/5" for d in DIMS) + "\nmissing:license"
    assert "Output check failed" not in after_model_callback(None, _resp(full)).content.parts[0].text


def test_non_report_reply_is_redacted_but_not_checked():
    text = after_model_callback(None, _resp("Which repository path? key sk-abcdefghijklmnopqrstuv")).content.parts[0].text
    assert "[REDACTED]" in text and "Output check failed" not in text


def test_reported_scores_are_held_to_scan_repo():
    scan = {"dimensions": [{"name": d, "score": 0, "issues": ["missing:license"]} for d in DIMS]}
    ctx = Ctx()
    # The real MCP result carries the JSON in a text block (no structuredContent).
    after_tool_callback(Tool("scan_repo"), {}, ctx, {"content": [{"type": "text", "text": json.dumps(scan)}], "isError": False})
    assert ctx.state["temp:scores"] == dict.fromkeys(DIMS, 0)
    report = "\n".join(f"## {d} — {5 if i == 0 else 0}/5" for i, d in enumerate(DIMS)) + "\nmissing:license"
    text = after_model_callback(ctx, _resp(report)).content.parts[0].text
    assert "## Usefulness & clarity — 0/5" in text and "5/5" not in text.split("\n\n>")[0]
    assert "Scores corrected to match `scan_repo`: Usefulness & clarity 5→0" in text


def test_perfect_repo_needs_no_citations():
    scan = {"dimensions": [{"name": d, "score": 5, "issues": []} for d in DIMS]}
    ctx = Ctx()
    after_tool_callback(Tool("scan_repo"), {}, ctx, {"content": [{"type": "text", "text": json.dumps(scan)}]})
    report = "\n".join(f"## {d} — 5/5" for d in DIMS) + "\n## Top 5 fixes\nNothing to fix."
    assert "Output check failed" not in after_model_callback(ctx, _resp(report)).content.parts[0].text


def test_before_model_callback_caps_calls(monkeypatch):
    from reviewer.guardrails import before_model_callback

    monkeypatch.setenv("MAX_LLM_CALLS", "2")
    ctx = Ctx()
    assert before_model_callback(ctx, None) is None
    assert before_model_callback(ctx, None) is None
    assert "call limit" in before_model_callback(ctx, None).content.parts[0].text


GOOD_URLS = ["https://github.com/pallets/flask", "https://github.com/pallets/flask.git", "https://github.com/a/b.c/"]
BAD_URLS = ["http://github.com/a/b", "https://github.com/a", "https://github.com/a/b/tree/main", "file:///etc",
            "https://github.com.evil.com/a/b", "git@github.com:a/b", "https://x@github.com/a/b", "--upload-pack=x",
            "https://github.com/a/..", "https://github.com/-a/b", "https://github.com/a/b?x=1"]


def test_github_url_allow_list():
    assert [parse_github_url(u) for u in GOOD_URLS] == [("pallets", "flask"), ("pallets", "flask"), ("a", "b.c")]
    for bad in BAD_URLS:
        with pytest.raises(ValueError):
            parse_github_url(bad)
        assert "error" in before_tool_callback(Tool("clone_repo"), {"url": bad}, None)
    assert before_tool_callback(Tool("clone_repo"), {"url": GOOD_URLS[0]}, None) is None


def test_clone_dir_is_inside_the_sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("CLONE_DIR", str(tmp_path / "clones"))
    (tmp_path / "clones" / "a__b").mkdir(parents=True)
    assert safe_path(str(tmp_path / "clones" / "a__b")) == (tmp_path / "clones" / "a__b").resolve()
    with pytest.raises(PermissionError):
        safe_path(str(tmp_path))


def test_clone_repo_runs_a_locked_down_shallow_clone(tmp_path, monkeypatch):
    monkeypatch.setenv("CLONE_DIR", str(tmp_path))
    calls = []

    def fake_run(cmd, env, **kw):
        calls.append((cmd, env))
        Path(cmd[-1]).mkdir()

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = clone_repo("https://github.com/Pallets/Flask.git/")
    cmd, env = calls[0]
    assert out["path"] == str(tmp_path.resolve() / "pallets__flask")
    assert cmd[-2] == "https://github.com/Pallets/Flask.git" and "--depth" in cmd and "credential.helper=" in cmd
    assert env["GIT_TERMINAL_PROMPT"] == "0"

    def failing_run(cmd, env, **kw):
        Path(cmd[-1]).mkdir()
        raise subprocess.CalledProcessError(128, cmd)

    monkeypatch.setattr(subprocess, "run", failing_run)
    with pytest.raises(ValueError, match="clone failed"):
        clone_repo("https://github.com/a/private")
    assert not (tmp_path / "a__private").exists()
