import os
from types import SimpleNamespace

import pytest

from review_core.safety import guardrails
from review_core.models import get_model
from review_core.analysis.tools import (
    check_manifest,
    check_risky_code,
    list_project_files,
    read_file,
    resolve_path,
    scan_for_secrets,
)


# ---- path resolution and sandbox ------------------------------------------- #
def test_bare_name_resolves_under_root(tmp_path):
    (tmp_path / "template").mkdir()
    path, err = resolve_path("template")
    assert err is None and path == (tmp_path / "template").resolve()


def test_name_resolves_under_agents_and_tools(tmp_path):
    (tmp_path / "agents" / "foo").mkdir(parents=True)
    (tmp_path / "tools" / "bar").mkdir(parents=True)
    assert resolve_path("foo")[0] == (tmp_path / "agents" / "foo").resolve()
    assert resolve_path("bar")[0] == (tmp_path / "tools" / "bar").resolve()


def test_repo_folder_name_resolves_to_root(tmp_path):
    path, err = resolve_path(tmp_path.name)
    assert err is None and path == tmp_path.resolve()


def test_quotes_are_stripped(tmp_path):
    (tmp_path / "template").mkdir()
    assert resolve_path("'template'")[1] is None


def test_path_outside_root_denied(tmp_path):
    outside = tmp_path.parent
    assert "outside the allowed root" in resolve_path(str(outside))[1]["error"]
    assert "error" in list_project_files("/etc")


def test_dotdot_escape_denied(tmp_path):
    (tmp_path / "proj").mkdir()
    assert "error" in resolve_path("proj/../..")[1] or resolve_path("proj/../..")[0] is None


def test_symlink_escape_denied(tmp_path_factory, tmp_path):
    secret_dir = tmp_path_factory.mktemp("outside")
    (secret_dir / "data.txt").write_text("private")
    (tmp_path / "link").symlink_to(secret_dir)
    assert "outside the allowed root" in resolve_path("link")[1]["error"]


def test_symlinks_not_followed_in_scans(tmp_path_factory, tmp_path):
    outside = tmp_path_factory.mktemp("outside")
    (outside / "leak.py").write_text('KEY = "AIza' + "B" * 35 + '"\n')
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "linked.py").symlink_to(outside / "leak.py")
    (proj / "linkdir").symlink_to(outside)
    assert scan_for_secrets(str(proj))["clean"]
    assert list_project_files(str(proj))["files"] == []


def test_missing_path_error_has_hint():
    err = check_manifest("does-not-exist")
    assert "error" in err and "hint" in err


# ---- read_file guardrails --------------------------------------------------- #
def test_read_file_refuses_secret_files(tmp_path):
    for name in (".env", ".env.local", "id_rsa", "server.pem", "credentials.json"):
        (tmp_path / name).write_text("SECRET=1")
        assert "Refused" in read_file(name)["error"], name


def test_read_file_allows_env_example_and_marks_untrusted(tmp_path):
    (tmp_path / ".env.example").write_text("KEY=placeholder")
    result = read_file(".env.example")
    assert result["content"] == "KEY=placeholder"
    assert "UNTRUSTED" in result["note"]


def test_read_file_redacts_keys(tmp_path):
    fake = "AIza" + "C" * 35
    (tmp_path / "notes.md").write_text(f"my key {fake} here")
    result = read_file("notes.md")
    assert fake not in result["content"] and "[REDACTED]" in result["content"]


def test_read_file_outside_root_denied():
    assert "error" in read_file("/etc/passwd")


# ---- risky code ------------------------------------------------------------- #
def test_risky_code_detected(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    # fixtures are assembled from parts so this test file is not itself flagged by the scanner
    code = "import os\nos.sys" + "tem('ls')\nsubprocess.run(x, shell=" + "True)\nev" + "al(y)\n"
    (proj / "run.py").write_text(code)
    issues = {f["issue"] for f in check_risky_code(str(proj))["findings"]}
    assert {"os system call", "shell execution via subprocess", "eval/exec call"} <= issues


def test_clean_code_not_flagged(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "ok.py").write_text("import subprocess\nsubprocess.run(['git', 'status'])\nmodel.evaluate(x)\n")
    assert check_risky_code(str(proj))["clean"]


# ---- tool-call limiter ------------------------------------------------------ #
def ctx(run="r1", agent="a1"):
    return SimpleNamespace(invocation_id=run, agent_name=agent)


def test_call_limit_enforced_per_agent(monkeypatch):
    monkeypatch.setattr(guardrails, "MAX_CALLS", 3)
    guardrails._calls.clear()
    for _ in range(3):
        assert guardrails.limit_tool_calls(None, {"path": "x"}, ctx()) is None
    assert "limit reached" in guardrails.limit_tool_calls(None, {"path": "x"}, ctx())["error"]
    # a different agent or run has its own budget
    assert guardrails.limit_tool_calls(None, {"path": "x"}, ctx(agent="a2")) is None
    assert guardrails.limit_tool_calls(None, {"path": "x"}, ctx(run="r2")) is None


def test_oversized_argument_refused():
    guardrails._calls.clear()
    result = guardrails.limit_tool_calls(None, {"path": "x" * 501}, ctx())
    assert "too long" in result["error"]


# ---- model configuration ---------------------------------------------------- #
@pytest.fixture
def clean_model_env(monkeypatch):
    for var in ("MODEL_PROVIDER", "MODEL_NAME", "NVIDIA_API_KEY", "NVIDIA_BASE_URL"):
        monkeypatch.delenv(var, raising=False)


def test_default_is_gemini(clean_model_env):
    assert get_model() == "gemini-2.5-flash"


def test_gemini_model_name_override(clean_model_env, monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "gemini-2.5-pro")
    assert get_model() == "gemini-2.5-pro"


def test_nvidia_requires_model_and_key(clean_model_env, monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "nvidia")
    with pytest.raises(ValueError, match="MODEL_NAME"):
        get_model()
    monkeypatch.setenv("MODEL_NAME", "some/model")
    with pytest.raises(ValueError, match="NVIDIA_API_KEY"):
        get_model()


def test_nvidia_builds_litellm_model(clean_model_env, monkeypatch):
    pytest.importorskip("litellm")
    monkeypatch.setenv("MODEL_PROVIDER", "nvidia")
    monkeypatch.setenv("MODEL_NAME", "some/model")
    monkeypatch.setenv("NVIDIA_API_KEY", "test-not-a-real-key")
    model = get_model()
    assert type(model).__name__ == "LiteLlm"
    assert model.model == "openai/some/model"


def test_unknown_provider_rejected(clean_model_env, monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "bogus")
    with pytest.raises(ValueError, match="Unknown MODEL_PROVIDER"):
        get_model()


def test_generated_folder_is_skipped_like_a_cache(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".generated" / "sample").mkdir(parents=True)
    (proj / ".generated" / "sample" / "leak.py").write_text('KEY = "AIza' + "B" * 35 + '"\n')
    (proj / "README.md").write_text("hi")
    assert scan_for_secrets(str(proj))["clean"]
    assert list_project_files(str(proj))["files"] == ["README.md"]


# ---- did-you-mean ------------------------------------------------------------ #
def test_typo_suggests_the_closest_folder(tmp_path):
    (tmp_path / "agents" / "readme-reviewer").mkdir(parents=True)
    _, err = resolve_path("readme-reviwer")
    assert err["did_you_mean"] == "agents/readme-reviewer"
    assert "Did you mean 'agents/readme-reviewer'?" in err["error"]


def test_typo_in_a_nested_path_compares_the_last_part(tmp_path):
    (tmp_path / "template").mkdir()
    _, err = resolve_path("agents/templat")
    assert err["did_you_mean"] == "template"


def test_unrelated_name_gets_no_suggestion(tmp_path):
    (tmp_path / "template").mkdir()
    _, err = resolve_path("zzzzzzzz")
    assert "did_you_mean" not in err and "Did you mean" not in err["error"]


def test_suggestions_ignore_hidden_and_skipped_folders(tmp_path):
    for name in (".git", ".venv", "node_modules", "__pycache__"):
        (tmp_path / name).mkdir()
    _, err = resolve_path("node_module")
    assert "did_you_mean" not in err


def test_suggestions_never_point_outside_the_root(tmp_path_factory, tmp_path):
    outside = tmp_path_factory.mktemp("outside")
    (outside / "secret-project").mkdir()
    (tmp_path / "link-to-outside").symlink_to(outside / "secret-project")
    _, err = resolve_path("secret-projec")
    assert "did_you_mean" not in err
