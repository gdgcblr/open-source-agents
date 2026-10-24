import json
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from agents.gitpulse.core import (
    GitPulseError,
    redact_sensitive_values,
    run_gitleaks_git_scanner,
    run_gitleaks_scanner,
    scan_diff,
)


def test_scanner_reports_added_credentials_without_exposing_value() -> None:
    fake_value = "synthetic-" + "credential-value"
    key_name = "api" + "_key"
    diff = (
        "diff --git a/src/config.py b/src/config.py\n"
        "--- a/src/config.py\n"
        "+++ b/src/config.py\n"
        "@@ -1,2 +1,3 @@\n"
        " unchanged = True\n"
        f'+{key_name} = "{fake_value}"\n'
    )

    findings = scan_diff(diff)
    redacted = redact_sensitive_values(diff)

    assert len(findings) == 1
    assert findings[0].category == "hardcoded-credential"
    assert findings[0].file_path == "src/config.py"
    assert findings[0].line_number == 2
    assert fake_value not in findings[0].message
    assert fake_value not in redacted
    assert "[REDACTED]" in redacted


def test_scanner_ignores_removed_lines_and_diff_headers() -> None:
    removed_line = "-pass" + "word = \"" + "synthetic-" + "credential-value\"\n"
    diff = (
        "--- a/old.py\n"
        "+++ b/new.py\n"
        "@@ -1 +1 @@\n"
        + removed_line
        + "+safe = True\n"
    )

    assert scan_diff(diff) == []


def test_scanner_reports_eval_and_ignores_placeholder_credentials() -> None:
    key_name = "api" + "_key"
    dynamic_call = "ev" + "al(user_input)"
    diff = (
        "+++ b/app.py\n"
        "@@ -0,0 +1,2 @@\n"
        f'+{key_name} = "your_api_key_here"\n'
        f"+{dynamic_call}\n"
    )

    findings = scan_diff(diff)

    assert [finding.category for finding in findings] == ["dynamic-code-execution"]
    assert findings[0].line_number == 2


def test_redactor_removes_private_key_block_contents() -> None:
    key_begin = "-----BEGIN " + "PRIVATE KEY-----"
    key_end = "-----END " + "PRIVATE KEY-----"
    diff = (
        "+++ b/key.txt\n"
        "@@ -0,0 +1,3 @@\n"
        f"+{key_begin}\n"
        "+synthetic-private-key-material\n"
        f"+{key_end}\n"
    )

    redacted = redact_sensitive_values(diff)

    assert "synthetic-private-key-material" not in redacted
    assert redacted.count("[REDACTED PRIVATE KEY") == 3


def test_redactor_preserves_file_headers_and_scans_plus_prefixed_source() -> None:
    fake_value = "synthetic-" + "credential-value"
    key_name = "api" + "_key"
    diff = (
        "diff --git a/config.py b/config.py\n"
        "--- a/config.py\n"
        "+++ b/config.py\n"
        "@@ -0,0 +1 @@\n"
        f'+++ {key_name} = "{fake_value}"\n'
    )

    findings = scan_diff(diff)
    redacted = redact_sensitive_values(diff)

    assert len(findings) == 1
    assert findings[0].file_path == "config.py"
    assert fake_value not in redacted
    assert "+++ b/config.py" in redacted
    assert f'+++ {key_name} = "[REDACTED]"' in redacted


def test_gitleaks_backend_normalizes_findings_without_exposing_secret() -> None:
    sample_value = "synthetic-" + "gitleaks-secret-value"

    def gitleaks_call(command: list[str], **_: object) -> CompletedProcess[str]:
        report_argument = next(argument for argument in command if argument.startswith("--report-path="))
        report_path = Path(report_argument.split("=", maxsplit=1)[1])
        report_path.write_text(
            json.dumps(
                [
                    {
                        "RuleID": "generic-api-key",
                        "File": "stdin",
                        "StartLine": 4,
                        "Secret": sample_value,
                        "Match": f"token = {sample_value}",
                    }
                ]
            ),
            encoding="utf-8",
        )
        return CompletedProcess(args=command, returncode=1, stdout="", stderr="")

    with patch("agents.gitpulse.core.subprocess.run", side_effect=gitleaks_call) as run:
        findings = run_gitleaks_scanner("diff --git a/app.py b/app.py\n+redacted input\n")

    assert len(findings) == 1
    assert findings[0].category == "gitleaks:generic-api-key"
    assert findings[0].file_path == "stdin"
    assert findings[0].line_number == 4
    assert sample_value not in findings[0].message
    assert run.call_args.kwargs["shell"] is False
    assert "--redact=100" in run.call_args.args[0]


def test_gitleaks_backend_accepts_clean_report(tmp_path: Path) -> None:
    def gitleaks_call(command: list[str], **_: object) -> CompletedProcess[str]:
        report_argument = next(argument for argument in command if argument.startswith("--report-path="))
        Path(report_argument.split("=", maxsplit=1)[1]).write_text("[]", encoding="utf-8")
        return CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    with patch("agents.gitpulse.core.subprocess.run", side_effect=gitleaks_call):
        assert run_gitleaks_scanner("diff --git a/app.py b/app.py\n") == []


def test_gitleaks_backend_reports_missing_executable() -> None:
    with patch(
        "agents.gitpulse.core.subprocess.run",
        side_effect=FileNotFoundError,
    ), pytest.raises(GitPulseError, match="Gitleaks was not found"):
        run_gitleaks_scanner("diff")


def test_gitleaks_git_backend_scans_the_resolved_commit_range(tmp_path: Path) -> None:
    fake_secret = "synthetic-" + "gitleaks-secret-value"

    def gitleaks_call(command: list[str], **_: object) -> CompletedProcess[str]:
        report_argument = next(argument for argument in command if argument.startswith("--report-path="))
        report_path = Path(report_argument.split("=", maxsplit=1)[1])
        report_path.write_text(
            json.dumps(
                [
                    {
                        "RuleID": "generic-api-key",
                        "File": "src/config.py",
                        "StartLine": 7,
                        "Secret": fake_secret,
                    }
                ]
            ),
            encoding="utf-8",
        )
        return CompletedProcess(args=command, returncode=1, stdout="", stderr="")

    with (
        patch(
            "agents.gitpulse.core._get_diff_context",
            return_value=(tmp_path, "b" * 40, "d" * 40, "a" * 40),
        ),
        patch("agents.gitpulse.core.subprocess.run", side_effect=gitleaks_call) as run,
    ):
        findings = run_gitleaks_git_scanner("upstream/main", "feature/topic", tmp_path)

    command = run.call_args.args[0]
    assert command[1] == "git"
    assert f"--log-opts={'b' * 40}..{'d' * 40}" in command
    assert str(tmp_path.resolve()) in command
    assert findings[0].file_path == "src/config.py"
    assert fake_secret not in findings[0].message