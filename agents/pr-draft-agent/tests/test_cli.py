"""CLI ordering, exit codes, stdout/stderr discipline, and configuration."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pr_draft_agent import __main__ as cli
from pr_draft_agent import config
from pr_draft_agent.config import Settings
from pr_draft_agent.output import VERIFICATION_NOTICE
from pr_draft_agent.repository import ChangedFile, InputError, RepositorySnapshot

NOTICE = VERIFICATION_NOTICE

DRAFT = """\
# Handle missing configuration files clearly

## Summary

Raise a clear error when the configuration file is absent.

## Why

Motivation was not provided by the author.

## Testing

- [x] Unit tests were added
- [ ] Run the test suite locally
"""


def _snapshot() -> RepositorySnapshot:
    return RepositorySnapshot(
        root=Path("/private/example/repository"),
        files=(ChangedFile("config_loader.py", "100644", "100644", "M"),),
        diff="+raise FileNotFoundError(path)\n",
        diff_sha256="a" * 64,
        template="## Summary\n\n## Why\n\n## Testing\n",
        template_source=".github/PULL_REQUEST_TEMPLATE.md",
    )


def test_check_is_local_and_prints_metadata_only(monkeypatch, capsys):
    monkeypatch.setattr(cli, "capture_snapshot", lambda repo: _snapshot())
    monkeypatch.setattr(cli, "load_settings", lambda require_model: pytest.fail("no config"))
    monkeypatch.setattr(cli, "generate_draft", pytest.fail)

    assert cli.main(["--repo", "/tmp/ignored", "--check"]) == 0

    captured = capsys.readouterr()
    assert "Eligible: yes" in captured.out
    assert "  M config_loader.py" in captured.out
    assert "Diff SHA-256: " + "a" * 64 in captured.out
    assert "raise FileNotFoundError" not in captured.out
    assert captured.err == ""


def test_generation_requires_explicit_send_flag(monkeypatch):
    monkeypatch.setattr(cli, "capture_snapshot", lambda repo: _snapshot())
    with pytest.raises(SystemExit) as exc:
        cli.main(["--repo", "/tmp/ignored"])
    assert exc.value.code == 2


def test_send_and_check_are_mutually_exclusive(monkeypatch):
    monkeypatch.setattr(cli, "capture_snapshot", lambda repo: _snapshot())
    with pytest.raises(SystemExit) as exc:
        cli.main(["--repo", "/tmp/ignored", "--check", "--send-to-model"])
    assert exc.value.code == 2


def test_send_to_model_prints_notice_and_valid_draft(monkeypatch, capsys):
    seen: dict[str, object] = {}

    async def fake_generate(snapshot, intent, model):
        seen.update(snapshot=snapshot, intent=intent, model=model)
        return DRAFT

    monkeypatch.setattr(cli, "capture_snapshot", lambda repo: _snapshot())
    monkeypatch.setattr(cli, "load_settings", lambda require_model: Settings("fake-model"))
    monkeypatch.setattr(cli, "generate_draft", fake_generate)

    code = cli.main(["--repo", "/tmp/ignored", "--send-to-model", "--intent", "  be clear  "])

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.startswith("# Handle missing configuration files clearly\n")
    assert "- [ ] Unit tests were added" in captured.out
    assert "- [x]" not in captured.out
    assert captured.out.count(NOTICE) == 1
    assert "Sending the staged diff" in captured.err
    assert "Generated a draft" in captured.err
    assert seen["intent"] == "  be clear  "
    assert seen["model"] == "fake-model"


def test_missing_credentials_never_call_the_model(monkeypatch, capsys):
    def fail_generate(*args, **kwargs):
        pytest.fail("generation must not start")

    def fail_settings(require_model):
        raise config.ConfigError("MISSING_CREDENTIALS", "GOOGLE_API_KEY is not set.")

    monkeypatch.setattr(cli, "capture_snapshot", lambda repo: _snapshot())
    monkeypatch.setattr(cli, "load_settings", fail_settings)
    monkeypatch.setattr(cli, "generate_draft", fail_generate)

    assert cli.main(["--repo", "/tmp/ignored", "--send-to-model"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "MISSING_CREDENTIALS" in captured.err


def test_capture_error_keeps_stdout_empty(monkeypatch, capsys):
    def fail_capture(repo):
        raise InputError("NO_STAGED_CHANGES", "No staged changes were found.")

    monkeypatch.setattr(cli, "capture_snapshot", fail_capture)
    assert cli.main(["--repo", "/tmp/ignored", "--check"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "NO_STAGED_CHANGES" in captured.err


def test_oversized_intent_is_rejected_before_generation(monkeypatch, capsys):
    async def fail_generate(*args, **kwargs):
        pytest.fail("generation must not start")

    monkeypatch.setattr(cli, "capture_snapshot", lambda repo: _snapshot())
    monkeypatch.setattr(cli, "load_settings", lambda require_model: Settings("fake-model"))
    monkeypatch.setattr(cli, "generate_draft", fail_generate)

    code = cli.main(["--repo", "/tmp/ignored", "--send-to-model", "--intent", "x" * 2049])
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "INPUT_TOO_LARGE" in captured.err


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (cli.GenerationError("AUTH_FAILED", "Authentication failed."), 3),
        (cli.GenerationError("RATE_LIMITED", "Rate limited."), 3),
        (cli.GenerationError("TOOLS_NOT_USED", "Both tools are required."), 4),
        (cli.OutputError("INVALID_DRAFT", "Missing title."), 4),
    ],
)
def test_known_errors_map_to_architecture_exit_codes(monkeypatch, capsys, error, expected):
    async def fail_generate(*args, **kwargs):
        raise error

    monkeypatch.setattr(cli, "capture_snapshot", lambda repo: _snapshot())
    monkeypatch.setattr(cli, "load_settings", lambda require_model: Settings("fake-model"))
    monkeypatch.setattr(cli, "generate_draft", fail_generate)

    assert cli.main(["--repo", "/tmp/ignored", "--send-to-model"]) == expected
    assert capsys.readouterr().out == ""


def test_invalid_output_never_reaches_stdout(monkeypatch, capsys):
    async def bad_generate(*args, **kwargs):
        return "No title here"

    monkeypatch.setattr(cli, "capture_snapshot", lambda repo: _snapshot())
    monkeypatch.setattr(cli, "load_settings", lambda require_model: Settings("fake-model"))
    monkeypatch.setattr(cli, "generate_draft", bad_generate)

    assert cli.main(["--repo", "/tmp/ignored", "--send-to-model"]) == 4
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "INVALID_DRAFT" in captured.err


def test_keyboard_interrupt_returns_130(monkeypatch, capsys):
    async def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "capture_snapshot", lambda repo: _snapshot())
    monkeypatch.setattr(cli, "load_settings", lambda require_model: Settings("fake-model"))
    monkeypatch.setattr(cli, "generate_draft", interrupted)

    assert cli.main(["--repo", "/tmp/ignored", "--send-to-model"]) == 130
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "INTERRUPTED" in captured.err


def test_unexpected_generation_failure_is_sanitized(monkeypatch, capsys):
    async def explode(*args, **kwargs):
        raise RuntimeError("SECRET_SENTINEL")

    monkeypatch.setattr(cli, "capture_snapshot", lambda repo: _snapshot())
    monkeypatch.setattr(cli, "load_settings", lambda require_model: Settings("fake-model"))
    monkeypatch.setattr(cli, "generate_draft", explode)

    assert cli.main(["--repo", "/tmp/ignored", "--send-to-model"]) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "SECRET_SENTINEL" not in captured.err
    assert "Traceback" not in captured.err


def test_settings_without_generation_do_not_require_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "absent.env")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("PR_DRAFT_MODEL", raising=False)
    settings = config.load_settings(require_model=False)
    assert settings.model is None


def test_settings_require_key_and_model(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "absent.env")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("PR_DRAFT_MODEL", raising=False)
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)

    with pytest.raises(config.ConfigError) as missing_key:
        config.load_settings(require_model=True)
    assert missing_key.value.code == "MISSING_CREDENTIALS"

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    with pytest.raises(config.ConfigError) as missing_model:
        config.load_settings(require_model=True)
    assert missing_model.value.code == "MISSING_MODEL"

    monkeypatch.setenv("PR_DRAFT_MODEL", "gemini-test")
    assert config.load_settings(require_model=True) == Settings("gemini-test")


def test_vertex_mode_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "absent.env")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("PR_DRAFT_MODEL", "gemini-test")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")

    with pytest.raises(config.ConfigError) as exc:
        config.load_settings(require_model=True)
    assert exc.value.code == "VERTEX_UNSUPPORTED"


def test_target_repository_dotenv_is_never_loaded(monkeypatch, tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / ".env").write_text(
        "GOOGLE_API_KEY=target-secret\nPR_DRAFT_MODEL=target-model\n", encoding="utf-8"
    )
    monkeypatch.chdir(target)
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "absent.env")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("PR_DRAFT_MODEL", raising=False)

    assert config.load_settings(require_model=False).model is None
    with pytest.raises(config.ConfigError) as exc:
        config.load_settings(require_model=True)
    assert exc.value.code == "MISSING_CREDENTIALS"
    assert "target-secret" not in str(exc.value)


def test_check_rejects_oversized_whitespace_intent(monkeypatch, capsys):
    monkeypatch.setattr(cli, "capture_snapshot", lambda repo: _snapshot())
    assert cli.main(["--repo", "/tmp/ignored", "--check", "--intent", " " * 2049]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "INPUT_TOO_LARGE" in captured.err


def test_real_offline_check_uses_no_provider_and_prints_no_content(repo, stage, monkeypatch, capsys):
    from google import genai

    from pr_draft_agent import agent

    def forbidden(*args, **kwargs):
        pytest.fail("offline checks must not construct a runner or provider")

    stage("app.txt", "PRIVATE_SOURCE_SENTINEL\n")
    monkeypatch.setattr(agent, "Runner", forbidden)
    monkeypatch.setattr(genai, "Client", forbidden)
    monkeypatch.setattr(cli, "generate_draft", forbidden)
    monkeypatch.setattr(cli, "load_settings", forbidden)
    assert cli.main(["--repo", str(repo), "--check", "--intent", "  context  "]) == 0
    captured = capsys.readouterr()
    assert "  A app.txt" in captured.out
    assert "Intent bytes: 11" in captured.out
    assert "PRIVATE_SOURCE_SENTINEL" not in captured.out + captured.err
    assert captured.err == ""


def test_real_rejected_inputs_never_call_generation(repo, stage, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("rejected inputs must not construct model configuration or generate")

    stage(".env", "safe content\n")
    monkeypatch.setattr(cli, "load_settings", forbidden)
    monkeypatch.setattr(cli, "generate_draft", forbidden)
    assert cli.main(["--repo", str(repo), "--send-to-model"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "SENSITIVE_INPUT" in captured.err


def test_process_environment_wins_over_project_dotenv(monkeypatch, tmp_path):
    local_env = tmp_path / "agent.env"
    local_env.write_text("GOOGLE_API_KEY=local-test-key\nPR_DRAFT_MODEL=local-test-model\n")
    monkeypatch.setattr(config, "ENV_FILE", local_env)
    monkeypatch.setenv("GOOGLE_API_KEY", "process-test-key")
    monkeypatch.setenv("PR_DRAFT_MODEL", "process-test-model")
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
    assert config.load_settings(require_model=True).model == "process-test-model"
    assert os.environ["GOOGLE_API_KEY"] == "process-test-key"


def test_provider_debug_logs_are_suppressed_even_with_existing_handlers(monkeypatch, capsys):
    import logging
    import sys

    names = (
        "google_adk.google.adk.models.google_llm",
        "google_genai._api_client",
        "google.auth.transport.requests",
        "httpx",
        "httpcore.connection",
    )
    loggers = [logging.getLogger(name) for name in names]
    previous = [(logger.handlers[:], logger.level, logger.propagate) for logger in loggers]
    for logger in loggers:
        logger.handlers[:] = [logging.StreamHandler(sys.stderr)]
        logger.setLevel(logging.DEBUG)
        logger.propagate = True

    async def noisy_generate(*args):
        for logger in loggers:
            logger.debug("PRIVATE_PROVIDER_SENTINEL request contents")
            logger.error("PRIVATE_PROVIDER_SENTINEL provider exception")
        return DRAFT

    monkeypatch.setattr(cli, "capture_snapshot", lambda repo: _snapshot())
    monkeypatch.setattr(cli, "load_settings", lambda require_model: Settings("fake-model"))
    monkeypatch.setattr(cli, "generate_draft", noisy_generate)
    try:
        assert cli.main(["--repo", "/tmp/ignored", "--send-to-model"]) == 0
        captured = capsys.readouterr()
        assert "PRIVATE_PROVIDER_SENTINEL" not in captured.out + captured.err
        assert "Generated a draft" in captured.err
    finally:
        for logger, (handlers, level, propagate) in zip(loggers, previous, strict=True):
            logger.handlers[:] = handlers
            logger.setLevel(level)
            logger.propagate = propagate


def test_transmission_follows_all_local_validation(monkeypatch, capsys):
    stages = []

    def capture(repo):
        stages.append("snapshot")
        return _snapshot()

    def validate(intent):
        stages.append("intent")
        return intent

    def settings(require_model):
        assert require_model is True
        stages.append("settings")
        return Settings("fake-model")

    async def generate(*args):
        assert "Sending the staged diff" in capsys.readouterr().err
        stages.append("generation")
        return DRAFT

    monkeypatch.setattr(cli, "capture_snapshot", capture)
    monkeypatch.setattr(cli, "validate_intent", validate)
    monkeypatch.setattr(cli, "load_settings", settings)
    monkeypatch.setattr(cli, "generate_draft", generate)
    assert cli.main(["--repo", "/tmp/ignored", "--send-to-model"]) == 0
    assert stages == ["snapshot", "intent", "settings", "generation"]
