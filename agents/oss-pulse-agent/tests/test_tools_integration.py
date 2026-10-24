"""Integration tests for all 4 telemetry analyzers.

Validates:
1. Activity Analyzer: stats parsing, commit recency, issue/PR turnaround.
2. Security Scanner: Dependabot config parsing, CI/CD SAST detection, branch protection.
3. Documentation Checker: README header parsing, license identification, templates.
4. Community Analyzer: Bus factor calculation, good-first-issue opportunities.
"""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from tools.github_analyzer import analyze_activity, get_repository_metadata
from tools.security_scanner import check_security_configuration
from tools.doc_checker import inspect_documentation
from tools.community_analyzer import analyze_community


def test_activity_analyzer_integration():
    """Verify that Activity Analyzer correctly processes commit stats and PR/issue data."""
    mock_client = MagicMock()
    # Mock commit_activity: 52 weeks of 10 commits
    mock_client.get.side_effect = lambda path, params=None: {
        "/repos/test/repo/stats/commit_activity": [{"total": 10}] * 52,
        "/repos/test/repo/commits": [{"commit": {"author": {"date": "2026-10-20T12:00:00Z"}}}],
        "/repos/test/repo/issues": [
            {
                "created_at": "2026-10-01T00:00:00Z",
                "closed_at": "2026-10-02T12:00:00Z",
                "updated_at": "2026-10-02T12:00:00Z",
            }
        ],
        "/repos/test/repo/pulls": [
            {
                "created_at": "2026-10-01T00:00:00Z",
                "merged_at": "2026-10-03T00:00:00Z",
            }
        ],
        "/repos/test/repo/releases": [
            {"published_at": "2026-06-01T00:00:00Z"}
        ],
    }.get(path, [])

    metrics = analyze_activity("test", "repo", mock_client)
    assert metrics.commits_30d == 40
    assert metrics.commits_90d == 130
    assert metrics.commits_365d == 520
    assert metrics.issue_response_time_median_hours == 36.0
    assert metrics.pr_merge_time_median_hours == 48.0
    assert len(metrics.evidence) >= 3


def test_security_scanner_integration():
    """Verify that Security Scanner detects Dependabot, CodeQL, and manifests."""
    mock_client = MagicMock()
    mock_client.get.side_effect = lambda path, params=None: {
        "/repos/test/repo/community/profile": {"files": {"security_policy": {"url": "https://..."}}},
        "/repos/test/repo": {"default_branch": "main"},
        "/repos/test/repo/branches/main/protection": {"enabled": True},
    }.get(path, None)

    mock_client.file_exists.side_effect = lambda o, r, p: p in ("SECURITY.md", "requirements.txt", "pyproject.toml")
    mock_client.get_file_content.side_effect = lambda o, r, p: (
        "version: 2\nupdates:\n  - package-ecosystem: 'pip'\n" if "dependabot" in p
        else "name: CodeQL\non: [push]\njobs:\n  analyze:\n    steps:\n      - uses: github/codeql-action/init" if "codeql" in p
        else None
    )
    mock_client.dir_listing.return_value = [{"name": "codeql.yml"}]

    config = check_security_configuration("test", "repo", mock_client)
    assert config.has_security_policy is True
    assert config.has_dependabot_config is True
    assert "pip" in config.dependabot_ecosystems
    assert config.has_code_scanning is True
    assert "CodeQL" in config.code_scanning_tools
    assert "requirements.txt" in config.dependency_manifests
    assert config.has_branch_protection is True


def test_doc_checker_integration():
    """Verify that Documentation Checker parses headers and identifies missing docs."""
    mock_client = MagicMock()
    mock_client.get.return_value = {"license": {"spdx_id": "MIT"}}
    mock_client.file_exists.side_effect = lambda o, r, p: p in ("CONTRIBUTING.md", "LICENSE")

    mock_readme = """# Sample Project
[![Build](https://img.shields.io/badge/status-ok-green)](#)
## Installation
Run `pip install sample`
## Usage
Import sample and run.
## Examples
```python
import sample
sample.run()
```
"""
    mock_client.get_file_content.side_effect = lambda o, r, p: mock_readme if "README" in p.upper() else None

    docs = inspect_documentation("test", "repo", mock_client)
    assert docs.has_readme is True
    assert docs.readme_has_badges is True
    assert docs.readme_has_installation is True
    assert docs.readme_has_usage is True
    assert docs.readme_has_examples is True
    assert docs.has_contributing is True
    assert docs.has_license is True
    assert docs.license_type == "MIT"


def test_community_analyzer_integration():
    """Verify that Community Analyzer calculates bus factor and extracts opportunities."""
    mock_client = MagicMock()
    mock_client.get.side_effect = lambda path, params=None: {
        "/repos/test/repo/contributors": [
            {"login": "alice", "contributions": 70},
            {"login": "bob", "contributions": 20},
            {"login": "charlie", "contributions": 10},
        ],
        "/repos/test/repo/stats/contributors": [
            {"author": {"login": "alice"}, "weeks": [{"c": 5}]}
        ],
        "/repos/test/repo": {"has_discussions": True},
        "/repos/test/repo/issues": [
            {
                "title": "Fix typo in docs",
                "html_url": "https://github.com/test/repo/issues/1",
                "labels": [{"name": "good first issue"}],
                "comments": 1,
                "assignee": None,
            }
        ],
    }.get(path, [])

    health = analyze_community("test", "repo", mock_client)
    assert health.total_contributors == 3
    assert health.bus_factor == 1  # Alice accounts for 70% (>= 50%)
    assert health.contributor_concentration == 0.7
    assert len(health.contribution_opportunities) >= 1
    assert health.contribution_opportunities[0].difficulty == "beginner"
