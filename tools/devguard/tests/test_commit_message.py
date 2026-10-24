"""Unit tests for DevGuard commit message generator and fallbacks."""

import pytest
from unittest.mock import MagicMock
from click.testing import CliRunner

from devguard.commit_message import (
    generate_commit_message,
    generate_commit_message_result,
    generate_fallback_message,
    generate_fallback_messages,
    detect_binary_files,
    MAX_DIFF_CHARS,
)
from devguard.cli import main


class DummyAIProvider:
    """Mock AI provider for testing."""
    def __init__(self, response: str = "feat(auth): add jwt authentication", should_fail: bool = False):
        self.response = response
        self.should_fail = should_fail
        self.last_prompt = None

    def generate(self, prompt: str) -> str:
        self.last_prompt = prompt
        if self.should_fail:
            raise RuntimeError("API quota exceeded")
        return self.response


def test_empty_diff_returns_empty_string():
    """Empty staged diff should produce empty message."""
    assert generate_commit_message("") == ""
    assert generate_commit_message("   ") == ""


def test_ai_provider_success():
    """When AI provider succeeds, its formatted message is returned."""
    mock_provider = DummyAIProvider("fix(cli): resolve flag parsing error")
    diff = "diff --git a/cli.py b/cli.py\n+fixed bug"
    msg = generate_commit_message(diff, provider=mock_provider)
    assert msg == "fix(cli): resolve flag parsing error"
    assert "diff --git a/cli.py" in mock_provider.last_prompt


def test_ai_provider_strips_markdown_codeblock():
    """If AI output includes markdown fencing, it should be cleanly stripped."""
    mock_provider = DummyAIProvider("```\nfeat: add support for new feature\n```")
    diff = "+new feature code"
    msg = generate_commit_message(diff, provider=mock_provider)
    assert msg == "feat: add support for new feature"


def test_ai_provider_failure_falls_back():
    """When AI provider fails, deterministic fallback should succeed."""
    failing_provider = DummyAIProvider(should_fail=True)
    diff = "diff --git a/README.md b/README.md\n+docs update"
    msg = generate_commit_message(diff, provider=failing_provider, fallback_on_error=True)
    assert msg.startswith(("docs:", "chore:", "test:"))


def test_diff_truncation_for_large_diff():
    """Diffs larger than MAX_DIFF_CHARS should be truncated before sending to model."""
    mock_provider = DummyAIProvider("refactor: massive overhaul")
    huge_diff = "a" * (MAX_DIFF_CHARS + 500)
    generate_commit_message(huge_diff, provider=mock_provider)
    assert "[staged diff truncated for length]" in mock_provider.last_prompt


def test_secret_redaction_in_ai_prompt():
    """Secrets present in staged diffs must be redacted before reaching the AI model."""
    mock_provider = DummyAIProvider("chore: add configuration")
    diff = (
        "diff --git a/config.py b/config.py\n"
        "+OPENAI_KEY = 'sk-1234567890123456789012345678901234567890'\n"
        "+DB_URL = 'postgres://admin:secret123@localhost:5432/db'\n"
    )
    generate_commit_message(diff, provider=mock_provider)
    # The prompt received by the provider MUST NOT contain the raw secrets
    assert "sk-1234567890" not in mock_provider.last_prompt
    assert "secret123" not in mock_provider.last_prompt
    assert "[REDACTED_OPENAI_KEY]" in mock_provider.last_prompt
    assert "[REDACTED_DB_PASSWORD]" in mock_provider.last_prompt


def test_detect_binary_files():
    """Detect binary files in git diff output."""
    diff = (
        "diff --git a/logo.png b/logo.png\n"
        "Binary files a/logo.png and b/logo.png differ\n"
        "diff --git a/test.py b/test.py\n"
        "+print('hello')\n"
    )
    detected = detect_binary_files(diff)
    assert "logo.png" in detected


def test_scope_in_fallback_and_ai():
    """Scope parameter is incorporated into message formatting."""
    # Fallback with scope
    msg = generate_fallback_messages(["README.md"], scope="docs", count=1)[0]
    assert msg.startswith("docs(docs):")

    # AI with scope
    mock_provider = DummyAIProvider("feat(auth): login with oauth2")
    diff = "+auth logic"
    res = generate_commit_message_result(diff, provider=mock_provider, scope="auth")
    assert "scope 'auth'" in mock_provider.last_prompt or "(auth)" in mock_provider.last_prompt
    assert res.candidates[0] == "feat(auth): login with oauth2"


def test_multiple_candidates_generation():
    """Multiple candidates are returned when requested."""
    # Deterministic fallback with 3 candidates
    candidates = generate_fallback_messages(["file1.py", "file2.py"], count=3)
    assert len(candidates) == 3
    assert all(c.startswith(("chore:", "feat:", "refactor:")) for c in candidates)

    # AI provider with 2 candidates
    mock_provider = DummyAIProvider("feat: candidate one\nrefactor: candidate two")
    diff = "+code"
    res = generate_commit_message_result(diff, provider=mock_provider, candidates_count=2)
    assert len(res.candidates) == 2
    assert res.candidates[0] == "feat: candidate one"
    assert res.candidates[1] == "refactor: candidate two"


def test_fallback_docs_heuristic():
    """Fallback accurately labels documentation changes."""
    files = ["README.md", "docs/index.md"]
    msg = generate_fallback_message(files)
    assert msg == "docs: update documentation (2 files)"


def test_fallback_test_heuristic():
    """Fallback accurately labels test changes."""
    files = ["tests/test_one.py", "tests/test_two.py"]
    msg = generate_fallback_message(files)
    assert msg == "test: update test suite (2 files)"


def test_fallback_config_heuristic():
    """Fallback accurately labels configuration changes."""
    files = ["devguard.yaml", "settings.json"]
    msg = generate_fallback_message(files)
    assert msg == "chore: update configuration (2 files)"


def test_fallback_single_file():
    """Fallback mentions single filename."""
    files = ["src/devguard/policy.py"]
    msg = generate_fallback_message(files)
    assert msg == "chore(policy): update policy.py"


def test_fallback_empty_files():
    """Fallback handles empty staged file list."""
    assert generate_fallback_message([]) == "chore: no changes staged"
