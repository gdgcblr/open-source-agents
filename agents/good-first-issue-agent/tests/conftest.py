"""Shared test helpers. No test touches the network or a real model."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeResponse:
    def __init__(self, status: int = 200, json_data: Any = None, headers: dict | None = None,
                 links: dict | None = None, text: str | None = None):
        self.status_code = status
        self._json = json_data
        self.headers = headers or {}
        self.links = links or {}
        self._text = text

    def json(self):
        if self._text is not None:
            raise ValueError("not json")
        return self._json


class FakeSession:
    """Returns queued responses (or raises queued exceptions) and records every call."""

    def __init__(self, responses: list[Any] | None = None, routes: dict[str, Any] | None = None):
        self.queue = list(responses or [])
        self.routes = routes or {}
        self.calls: list[dict[str, Any]] = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {}), "headers": dict(headers or {}), "timeout": timeout})
        for suffix, resp in self.routes.items():
            if url.endswith(suffix):
                return self._emit(resp)
        if not self.queue:
            raise AssertionError(f"unexpected request: {url}")
        return self._emit(self.queue.pop(0))

    @staticmethod
    def _emit(item):
        if isinstance(item, Exception):
            raise item
        return item


def gh_issue(number: int, title: str = "Issue", body: str | None = "", labels=(), pr: bool = False, **extra) -> dict:
    data = {
        "number": number,
        "title": title,
        "body": body,
        "html_url": f"https://github.com/o/r/issues/{number}",
        "labels": [{"name": n} for n in labels],
        "state": "open",
        "assignees": [],
        "comments": 0,
        "created_at": "2026-09-01T00:00:00Z",
        "updated_at": "2026-10-01T00:00:00Z",
        "locked": False,
    }
    if pr:
        data["pull_request"] = {"url": "x"}
    data.update(extra)
    return data


REPO_META = {
    "full_name": "o/r",
    "html_url": "https://github.com/o/r",
    "description": "A test repo",
    "language": "Python",
    "default_branch": "main",
    "archived": False,
    "has_issues": True,
    "open_issues_count": 3,
}


@pytest.fixture(autouse=True)
def _no_real_credentials(monkeypatch):
    """Make sure tests never pick up real tokens or keys from the environment."""
    for name in ("GITHUB_TOKEN", "GOOGLE_API_KEY", "GEMINI_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI",
                 "SENTRY_AUTH_TOKEN", "GLITCHTIP_AUTH_TOKEN", "SENTRY_ORG", "SENTRY_PROJECT",
                 "GLITCHTIP_ORG", "GLITCHTIP_PROJECT", "GLITCHTIP_URL", "SENTRY_URL", "GEMINI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("time.sleep", lambda *_: None)


__all__ = ["FakeResponse", "FakeSession", "gh_issue", "REPO_META", "requests"]
