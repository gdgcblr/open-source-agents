from pathlib import Path

import pytest
from google.adk.workflow._errors import DynamicNodeFailError

from agents.gitpulse import cli
from agents.gitpulse.agent import create_agent
from agents.gitpulse.core import GitPulseError, LintFinding, SecurityFinding


def _write_diff(path: Path) -> str:
    fake_value = "synthetic-" + "credential-value"
    key_name = "api" + "_key"
    path.write_text(
        "diff --git a/config.py b/config.py\n"
        "--- a/config.py\n"
        "+++ b/config.py\n"
        "@@ -0,0 +1 @@\n"
        f'+{key_name} = "{fake_value}"\n',
        encoding="utf-8",
    )
    return fake_value


def test_offline_cli_writes_report_without_running_model(tmp_path: Path, monkeypatch) -> None:
    diff_path = tmp_path / "change.diff"
    output_path = tmp_path / "review.md"
    _write_diff(diff_path)
    monkeypatch.setattr(cli, "run_model_review", lambda *_: (_ for _ in ()).throw(AssertionError()))

    exit_code = cli.main(
        ["review", "--diff-file", str(diff_path), "--mode", "offline", "--output", str(output_path)]
    )

    report = output_path.read_text(encoding="utf-8")
    assert exit_code == 1
    assert "AI analysis:** Skipped" in report
    assert "Heuristic findings" not in report
    assert "Possible hardcoded credential" in report


def test_model_failure_still_writes_scanner_findings(tmp_path: Path, monkeypatch) -> None:
    diff_path = tmp_path / "change.diff"
    output_path = tmp_path / "review.md"
    fake_value = _write_diff(diff_path)

    def fail_model(*_: object) -> None:
        raise RuntimeError("model is unavailable")

    monkeypatch.setattr(cli, "run_model_review", fail_model)
    exit_code = cli.main(
        ["review", "--diff-file", str(diff_path), "--mode", "ollama", "--output", str(output_path)]
    )

    report = output_path.read_text(encoding="utf-8")
    assert exit_code == 3
    assert "AI analysis:** Failed" in report
    assert "Possible hardcoded credential" in report
    assert fake_value not in report


def test_wrapped_adk_model_failure_writes_report_without_traceback(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    diff_path = tmp_path / "change.diff"
    _write_diff(diff_path)
    output_path = tmp_path / "review.md"

    def fail_model(*_: object) -> None:
        raise DynamicNodeFailError(
            message="provider request failed",
            error=RuntimeError("provider request failed"),
            error_node_path="gitpulse_reviewer",
        )

    monkeypatch.setattr(cli, "run_model_review", fail_model)
    exit_code = cli.main(
        ["review", "--diff-file", str(diff_path), "--mode", "gemini-api", "--output", str(output_path)]
    )

    report = output_path.read_text(encoding="utf-8")
    captured = capsys.readouterr()
    assert exit_code == 3
    assert "AI analysis:** Failed" in report
    assert "Possible hardcoded credential" in report
    assert "DynamicNodeFailError" in captured.err
    assert "Traceback" not in captured.err


def test_cli_refuses_overwriting_existing_report(tmp_path: Path) -> None:
    diff_path = tmp_path / "change.diff"
    output_path = tmp_path / "review.md"
    _write_diff(diff_path)
    output_path.write_text("keep me", encoding="utf-8")

    exit_code = cli.main(
        ["review", "--diff-file", str(diff_path), "--output", str(output_path)]
    )

    assert exit_code == 2
    assert output_path.read_text(encoding="utf-8") == "keep me"


def test_gemini_api_mode_requires_an_api_key(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        create_agent(mode="gemini-api")


def test_gemini_api_mode_builds_documented_model_without_network(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")

    agent = create_agent(mode="gemini-api", model_name="gemini-3.5-flash-lite")

    assert agent.model.model == "gemini-3.5-flash-lite"


def test_commit_linter_cli_accepts_and_rejects_headers(capsys) -> None:
    valid_status = cli.main(["lint-commit", "--message", "feat(gitpulse): add Ruff checks"])
    invalid_status = cli.main(["lint-commit", "--message", "feature: add a feature"])

    captured = capsys.readouterr()
    assert valid_status == 0
    assert invalid_status == 1
    assert "passes Conventional Commits lint" in captured.out
    assert "Unsupported type 'feature'" in captured.err


def test_branch_review_includes_ruff_findings_and_security_findings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    diff_path = tmp_path / "change.diff"
    _write_diff(diff_path)
    diff_text = diff_path.read_text(encoding="utf-8")
    output_path = tmp_path / "review.md"
    lint_finding = LintFinding("config.py", 2, "F401", "Unused import")
    monkeypatch.setattr(cli, "get_branch_diff", lambda *_args, **_kwargs: diff_text)
    monkeypatch.setattr(
        cli,
        "get_changed_python_files",
        lambda *_args, **_kwargs: (Path("config.py"),),
    )
    monkeypatch.setattr(cli, "run_ruff_linter", lambda *_args, **_kwargs: [lint_finding])

    exit_code = cli.main(
        [
            "review",
            "--base",
            "upstream/main",
            "--repository",
            str(tmp_path),
            "--mode",
            "offline",
            "--output",
            str(output_path),
        ]
    )

    report = output_path.read_text(encoding="utf-8")
    assert exit_code == 1
    assert "Python lint (Ruff):** Completed" in report
    assert "F401" in report
    assert "Possible hardcoded credential" in report


def test_ruff_failure_does_not_suppress_security_findings(tmp_path: Path, monkeypatch) -> None:
    diff_path = tmp_path / "change.diff"
    _write_diff(diff_path)
    diff_text = diff_path.read_text(encoding="utf-8")
    output_path = tmp_path / "review.md"
    monkeypatch.setattr(cli, "get_branch_diff", lambda *_args, **_kwargs: diff_text)
    monkeypatch.setattr(
        cli,
        "get_changed_python_files",
        lambda *_args, **_kwargs: (Path("config.py"),),
    )

    def fail_linter(*_: object, **__: object) -> list[LintFinding]:
        raise GitPulseError("Ruff unavailable")

    monkeypatch.setattr(cli, "run_ruff_linter", fail_linter)
    exit_code = cli.main(
        [
            "review",
            "--base",
            "upstream/main",
            "--repository",
            str(tmp_path),
            "--mode",
            "offline",
            "--output",
            str(output_path),
        ]
    )

    report = output_path.read_text(encoding="utf-8")
    assert exit_code == 4
    assert "Python lint (Ruff):** Failed" in report
    assert "Possible hardcoded credential" in report


def test_review_cli_accepts_local_head_ref(tmp_path: Path, monkeypatch) -> None:
    diff_path = tmp_path / "change.diff"
    _write_diff(diff_path)
    diff_text = diff_path.read_text(encoding="utf-8")
    output_path = tmp_path / "review.md"
    captured: dict[str, object] = {}

    def fake_get_diff(base_ref: str, repository: Path, **kwargs: object) -> str:
        captured.update(base_ref=base_ref, repository=repository, **kwargs)
        return diff_text

    monkeypatch.setattr(cli, "get_branch_diff", fake_get_diff)

    exit_code = cli.main(
        [
            "review",
            "--base",
            "upstream/main",
            "--head-ref",
            "feature/topic",
            "--repository",
            str(tmp_path),
            "--skip-python-lint",
            "--mode",
            "offline",
            "--output",
            str(output_path),
        ]
    )

    assert captured["head_ref"] == "feature/topic"
    assert "upstream/main...feature/topic" in output_path.read_text(encoding="utf-8")
    assert exit_code == 1


def test_review_cli_fetches_pr_head_from_selected_remote(tmp_path: Path, monkeypatch) -> None:
    diff_path = tmp_path / "change.diff"
    _write_diff(diff_path)
    diff_text = diff_path.read_text(encoding="utf-8")
    output_path = tmp_path / "review.md"
    fetch_call: dict[str, object] = {}
    diff_call: dict[str, object] = {}

    def fake_fetch(pr_number: int, remote: str, repository: Path) -> str:
        fetch_call.update(pr_number=pr_number, remote=remote, repository=repository)
        return "refs/gitpulse/pull/17/head"

    def fake_get_diff(base_ref: str, repository: Path, **kwargs: object) -> str:
        diff_call.update(base_ref=base_ref, repository=repository, **kwargs)
        return diff_text

    monkeypatch.setattr(cli, "fetch_pull_request_head", fake_fetch)
    monkeypatch.setattr(cli, "get_branch_diff", fake_get_diff)

    exit_code = cli.main(
        [
            "review",
            "--base",
            "upstream/main",
            "--pr-number",
            "17",
            "--remote",
            "upstream",
            "--repository",
            str(tmp_path),
            "--skip-python-lint",
            "--mode",
            "offline",
            "--output",
            str(output_path),
        ]
    )

    assert fetch_call["pr_number"] == 17
    assert fetch_call["remote"] == "upstream"
    assert diff_call["head_ref"] == "refs/gitpulse/pull/17/head"
    assert exit_code == 1


def test_branch_gitleaks_uses_git_history_scanner(tmp_path: Path, monkeypatch) -> None:
    diff_path = tmp_path / "change.diff"
    _write_diff(diff_path)
    diff_text = diff_path.read_text(encoding="utf-8")
    output_path = tmp_path / "review.md"
    scanner_call: dict[str, object] = {}

    def fake_get_diff(*_: object, **__: object) -> str:
        return diff_text

    def fake_gitleaks(base_ref: str, head_ref: str, repository: Path, **kwargs: object):
        scanner_call.update(base_ref=base_ref, head_ref=head_ref, repository=repository, **kwargs)
        return []

    monkeypatch.setattr(cli, "get_branch_diff", fake_get_diff)
    monkeypatch.setattr(cli, "run_gitleaks_git_scanner", fake_gitleaks)

    exit_code = cli.main(
        [
            "review",
            "--base",
            "upstream/main",
            "--head-ref",
            "feature/topic",
            "--repository",
            str(tmp_path),
            "--secret-scanner",
            "gitleaks",
            "--skip-python-lint",
            "--mode",
            "offline",
            "--output",
            str(output_path),
        ]
    )

    assert scanner_call["base_ref"] == "upstream/main"
    assert scanner_call["head_ref"] == "feature/topic"
    assert exit_code == 0


def test_gitleaks_finding_skips_model_and_keeps_secret_value_out_of_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    diff_path = tmp_path / "change.diff"
    secret_value = _write_diff(diff_path)
    output_path = tmp_path / "review.md"
    finding = SecurityFinding(
        category="gitleaks:generic-api-key",
        severity="high",
        file_path="stdin",
        line_number=4,
        message="Gitleaks detected a possible secret (rule generic-api-key); value redacted.",
    )

    def unexpected_model_call(*_: object, **__: object) -> None:
        raise AssertionError("Model must not receive a diff with a Gitleaks finding.")

    monkeypatch.setattr(cli, "run_gitleaks_scanner", lambda *_args, **_kwargs: [finding])
    monkeypatch.setattr(cli, "run_model_review", unexpected_model_call)
    exit_code = cli.main(
        [
            "review",
            "--diff-file",
            str(diff_path),
            "--secret-scanner",
            "gitleaks",
            "--mode",
            "gemini-api",
            "--output",
            str(output_path),
        ]
    )

    report = output_path.read_text(encoding="utf-8")
    assert exit_code == 1
    assert "Gitleaks detected a possible secret" in report
    assert "AI review was skipped because Gitleaks found possible secrets" in report
    assert secret_value not in report


def test_gitleaks_failure_skips_model_and_reports_incomplete_scan(
    tmp_path: Path,
    monkeypatch,
) -> None:
    diff_path = tmp_path / "change.diff"
    _write_diff(diff_path)
    output_path = tmp_path / "review.md"

    def missing_gitleaks(*_: object, **__: object):
        raise GitPulseError("Gitleaks was not found")

    def unexpected_model_call(*_: object, **__: object) -> None:
        raise AssertionError("Model must not run when Gitleaks did not complete.")

    monkeypatch.setattr(cli, "run_gitleaks_scanner", missing_gitleaks)
    monkeypatch.setattr(cli, "run_model_review", unexpected_model_call)
    exit_code = cli.main(
        [
            "review",
            "--diff-file",
            str(diff_path),
            "--secret-scanner",
            "gitleaks",
            "--mode",
            "ollama",
            "--output",
            str(output_path),
        ]
    )

    report = output_path.read_text(encoding="utf-8")
    assert exit_code == 5
    assert "Secret scanner:** gitleaks (Failed)" in report
    assert "the dedicated scan is not clean or verified" in report
    assert "AI review was skipped because the dedicated secret scan did not complete" in report