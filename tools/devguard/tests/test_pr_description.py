"""Tests for pull request description generator."""

from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from devguard.pr_description import (
    generate_pr_description,
    generate_fallback_pr_description,
    resolve_base_branch,
    get_verified_tests_from_audit,
    PRDescriptionResult,
)
from devguard.audit import record_audit
from devguard.cli import main


class MockPRProvider:
    """Mock AI provider returning PR Markdown."""

    def __init__(self, should_fail: bool = False, name: str = "gemini"):
        self.should_fail = should_fail
        self.name = name
        self.last_prompt = None

    def generate(self, prompt: str) -> str:
        self.last_prompt = prompt
        if self.should_fail:
            raise RuntimeError("API error")
        return (
            "# feat(tools): add devguard command manager\n\n"
            "## Summary of Changes\nAdds deterministic policy engine.\n\n"
            "## Key Implementation Details\nSafe subprocess execution.\n\n"
            "## Test Plan\n- [x] pytest tests/ [Verified locally in DevGuard audit]\n\n"
            "## Reviewer Checklist\n- [ ] Code style matches"
        )


def test_fallback_pr_description_structure():
    """Verify deterministic fallback generates required standard sections."""
    commits = ["a1b2c3d feat: add initial permissions", "e4f5g6h test: add test suite"]
    verified = ["pytest tests/ -v"]

    res = generate_fallback_pr_description(
        current_branch="feat/devguard",
        base_branch="main",
        commits=commits,
        verified_tests=verified,
    )
    assert isinstance(res, PRDescriptionResult)
    assert res.source == "deterministic-fallback"
    assert "## Summary of Changes" in res.markdown
    assert "## Key Implementation Details" in res.markdown
    assert "## Test Plan" in res.markdown
    assert "## Reviewer Checklist" in res.markdown
    assert "Verified passing in DevGuard local audit" in res.markdown
    assert "Suggested Verification Steps" in res.markdown


def test_verified_tests_distinguished_from_suggested(tmp_path: Path):
    """Passing test records in audit are identified as verified."""
    history_file = tmp_path / "audit.jsonl"
    record_audit(
        command=["pytest", "tests/test_policy.py"],
        executable="pytest",
        decision="ALLOW",
        approval_status="not_required",
        exit_code=0,
        history_path=history_file,
    )
    record_audit(
        command=["rm", "-rf", "temp"],
        executable="rm",
        decision="DENY",
        approval_status="not_required",
        exit_code=1,
        history_path=history_file,
    )

    with patch("devguard.pr_description.get_audit_history", side_effect=lambda limit: [
        {"command": ["pytest", "tests/test_policy.py"], "exit_code": 0},
        {"command": ["rm", "-rf"], "exit_code": 1},
    ]):
        verified = get_verified_tests_from_audit()
        assert "pytest tests/test_policy.py" in verified
        assert not any("rm -rf" in v for v in verified)


def test_secret_redaction_in_pr_description():
    """Secrets in branch diff must be redacted before sending to model."""
    mock_provider = MockPRProvider()
    with patch("devguard.pr_description.get_branch_diff", return_value="diff --git a/key.txt\n+GEMINI_KEY=AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q\n"), \
         patch("devguard.pr_description.get_branch_commits", return_value=["feat: add key"]):
        generate_pr_description(provider=mock_provider)

    assert mock_provider.last_prompt is not None
    assert "AIzaSy" not in mock_provider.last_prompt
    assert "[REDACTED_GEMINI_KEY]" in mock_provider.last_prompt


def test_pr_description_source_reflects_provider_name():
    """AI-assisted PR source label includes the provider name (e.g. ollama)."""
    mock_provider = MockPRProvider(name="ollama")
    with patch("devguard.pr_description.get_branch_diff", return_value="diff --git a/a.py\n+print(1)\n"), \
         patch("devguard.pr_description.get_branch_commits", return_value=["feat: x"]), \
         patch("devguard.pr_description.get_current_branch", return_value="feat/x"), \
         patch("devguard.pr_description.resolve_base_branch", return_value="main"):
        res = generate_pr_description(provider=mock_provider)

    assert res.source == "ai-assisted (ollama)"


def test_cli_pr_description_fallback_and_save(runner: CliRunner, tmp_path: Path):
    """Test 'devguard pr-description --fallback -o <file>' outputs and writes Markdown."""
    out_file = tmp_path / "PR_SUMMARY.md"
    with patch("devguard.pr_description.get_current_branch", return_value="feat/devguard"), \
         patch("devguard.pr_description.get_branch_commits", return_value=["feat: first commit"]):
        res = runner.invoke(
            main,
            ["pr-description", "--fallback", "-o", str(out_file)],
        )
        assert res.exit_code == 0
        assert "Pull Request Description" in res.output
        assert "Summary of Changes" in res.output
        assert out_file.exists()
        saved_text = out_file.read_text(encoding="utf-8")
        assert "## Reviewer Checklist" in saved_text

