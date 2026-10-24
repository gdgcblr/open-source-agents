"""Shared fixtures: a fake GitHub client and small builders for API-shaped payloads."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from issue_scout.github import GitHubClient, GitHubError  # noqa: E402

NOW = datetime(2026, 10, 24, 12, 0, 0, tzinfo=timezone.utc)


def ts(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeClient(GitHubClient):
    """Serves canned responses. Routes map a path to a value or to fn(params) -> value."""

    def __init__(self, routes=None, authenticated=False):
        super().__init__(token="fake-token" if authenticated else "")
        self.routes = dict(routes or {})
        self.calls = []

    def get(self, path, params=None):
        self.calls.append((path, dict(params or {})))
        self.requests_made += 1
        if path not in self.routes:
            raise GitHubError("Not Found: %s" % path, 404)
        value = self.routes[path]
        if isinstance(value, Exception):
            raise value
        return value(params or {}) if callable(value) else value


def comment(body, author="someone", role="NONE", days_ago=1.0, bot=False):
    return {
        "event": "commented",
        "body": body,
        "user": {"login": author, "type": "Bot" if bot else "User"},
        "author_association": role,
        "created_at": ts(days_ago),
        "html_url": "https://github.com/o/r/issues/1#issuecomment-%d" % abs(hash(body) % 10000),
    }


def cross_ref(number, state="open", merged=False, repo="o/r", is_pr=True, days_ago=2.0):
    issue = {
        "number": number,
        "title": "PR %d" % number,
        "state": state,
        "html_url": "https://github.com/%s/pull/%d" % (repo, number),
        "user": {"login": "dev%d" % number},
        "repository": {"full_name": repo},
    }
    if is_pr:
        issue["pull_request"] = {"merged_at": ts(1) if merged else None}
    return {"event": "cross-referenced", "created_at": ts(days_ago), "source": {"type": "issue", "issue": issue}}


def issue_payload(number, repo="o/r", title="Fix crash in parser", body=None, labels=("good first issue",),
                  comments=1, created=30, updated=3, assignees=(), state="open", locked=False):
    return {
        "number": number,
        "title": title,
        "body": body if body is not None else "Steps to reproduce: call `parse_config` with an empty file. " * 6,
        "html_url": "https://github.com/%s/issues/%d" % (repo, number),
        "repository_url": "https://api.github.com/repos/%s" % repo,
        "labels": [{"name": name} for name in labels],
        "comments": comments,
        "created_at": ts(created),
        "updated_at": ts(updated),
        "assignees": [{"login": login} for login in assignees],
        "state": state,
        "locked": locked,
    }


def repo_payload(name="o/r", stars=1500, archived=False):
    return {
        "full_name": name,
        "stargazers_count": stars,
        "pushed_at": ts(1),
        "archived": archived,
        "description": "demo",
        "default_branch": "main",
    }


def pull(role="CONTRIBUTOR", merged_days=None, bot=False, opened=10):
    return {
        "user": {"login": "bot[bot]" if bot else "person", "type": "Bot" if bot else "User"},
        "author_association": role,
        "created_at": ts(opened),
        "merged_at": ts(opened - merged_days) if merged_days is not None else None,
    }


@pytest.fixture
def now():
    return NOW
