"""Triage tests using a tiny synthetic recorded-JSON fixture (fully offline)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from contrib_audit.github_source import GitHubClient, triage_pr
from contrib_audit.models import Verdict


# ---------------------------------------------------------------------------
# Synthetic PR fixtures
# ---------------------------------------------------------------------------

GOOD_PR = {
    "number": 42,
    "title": "feat(agents): add research-assistant",
    "user": {"login": "alice"},
}

GOOD_FILES = [
    {
        "filename": "agents/research-assistant/README.md",
        "status": "added",
        "patch": "+# Research Assistant\n+## Overview\n",
    },
    {
        "filename": "agents/research-assistant/requirements.txt",
        "status": "added",
        "patch": "+google-adk>=1.0\n",
    },
    {
        "filename": "agents/research-assistant/.env.example",
        "status": "added",
        "patch": "+GOOGLE_API_KEY=your_key_here\n",
    },
    {
        "filename": "agents/research-assistant/.gitignore",
        "status": "added",
        "patch": "+.env\n",
    },
    {
        "filename": "agents/research-assistant/agent.py",
        "status": "added",
        "patch": "+from google.adk.agents import Agent\n",
    },
]

SECRET_PR = {
    "number": 99,
    "title": "feat(agents): add leaky-agent",
    "user": {"login": "bob"},
}

# Build fake secret at runtime from fragments
_FAKE_KEY = "AIza" + "Z" * 35

SECRET_FILES = [
    {
        "filename": "agents/leaky-agent/config.py",
        "status": "added",
        "patch": f'+API_KEY = "{_FAKE_KEY}"\n',
    },
    {
        "filename": "agents/leaky-agent/requirements.txt",
        "status": "added",
        "patch": "+google-adk>=1.0\n",
    },
]

OUT_OF_SCOPE_PR = {
    "number": 77,
    "title": "feat: add agent but also mess with CONTRIBUTING",
    "user": {"login": "charlie"},
}

OUT_OF_SCOPE_FILES = [
    {
        "filename": "agents/scope-agent/README.md",
        "status": "added",
        "patch": "+# Scope Agent\n",
    },
    {
        "filename": "CONTRIBUTING.md",   # <-- out of scope
        "status": "modified",
        "patch": "+Some change\n",
    },
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _mock_client(files_response: list) -> GitHubClient:
    client = MagicMock(spec=GitHubClient)
    client.get_pr_files.return_value = files_response
    return client


class TestTriagePR:
    def test_good_pr_ready_or_nits(self):
        client = _mock_client(GOOD_FILES)
        result = triage_pr(client, "owner", "repo", GOOD_PR)
        assert result["verdict"] in (Verdict.READY.value, Verdict.APPROVE_WITH_NITS.value)
        assert result["project_dir"] == "agents/research-assistant"

    def test_secret_pr_rejected(self):
        client = _mock_client(SECRET_FILES)
        result = triage_pr(client, "owner", "repo", SECRET_PR)
        assert result["verdict"] == Verdict.REJECT.value

    def test_out_of_scope_pr_changes_requested(self):
        client = _mock_client(OUT_OF_SCOPE_FILES)
        result = triage_pr(client, "owner", "repo", OUT_OF_SCOPE_PR)
        assert result["verdict"] in (
            Verdict.CHANGES_REQUESTED.value,
            Verdict.REJECT.value,
        )
        # CONTRIBUTING.md should be flagged
        assert any("CONTRIBUTING" in issue for issue in result.get("top_issues", []))

    def test_no_files(self):
        client = _mock_client([])
        result = triage_pr(client, "owner", "repo", GOOD_PR)
        # Should not crash; verdict not READY (no project dir found)
        assert result["verdict"] != Verdict.READY.value

    def test_pr_metadata_preserved(self):
        client = _mock_client(GOOD_FILES)
        result = triage_pr(client, "owner", "repo", GOOD_PR)
        assert result["pr"] == 42
        assert result["author"] == "alice"


class TestSummaries:
    def test_no_key_returns_empty_dict(self, monkeypatch):
        from contrib_audit.summaries import summarize_readmes
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        res = summarize_readmes({42: "README content"})
        assert res == {}

    def test_empty_input_returns_empty_dict(self, monkeypatch):
        from contrib_audit.summaries import summarize_readmes
        monkeypatch.setenv("GOOGLE_API_KEY", "fake_key_for_test")
        res = summarize_readmes({})
        assert res == {}

