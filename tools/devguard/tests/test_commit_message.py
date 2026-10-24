"""Unit tests for DevGuard commit message generator and fallbacks."""

import pytest
from unittest.mock import MagicMock
from devguard.commit_message import (
    generate_commit_message,
    generate_fallback_message,
    MAX_DIFF_CHARS,
)


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
    # Fallback without mock staged stats produces chore or docs
    msg = generate_commit_message(diff, provider=failing_provider, fallback_on_error=True)
    assert msg.startswith(("docs:", "chore:", "test:"))


def test_diff_truncation_for_large_diff():
    """Diffs larger than MAX_DIFF_CHARS should be truncated before sending to model."""
    mock_provider = DummyAIProvider("refactor: massive overhaul")
    huge_diff = "a" * (MAX_DIFF_CHARS + 500)
    generate_commit_message(huge_diff, provider=mock_provider)
    assert "[diff truncated for length]" in mock_provider.last_prompt


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
    assert msg == "chore: update policy.py"


def test_fallback_empty_files():
    """Fallback handles empty staged file list."""
    assert generate_fallback_message([]) == "chore: no changes staged"

