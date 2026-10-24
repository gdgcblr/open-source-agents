"""Minimal GitHub REST client built on the standard library.

Only public, read-only endpoints are used. A token is optional; without one
GitHub allows 60 core requests and 10 search requests per hour/minute, which is
enough for a small scouting run.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

API_ROOT = "https://api.github.com"
USER_AGENT = "issue-scout (+https://github.com/gdgcblr/open-source-agents)"


class GitHubError(RuntimeError):
    """Raised when GitHub returns an error response."""

    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


class RateLimitError(GitHubError):
    """Raised when the GitHub rate limit is exhausted."""


class GitHubClient:
    def __init__(self, token: Optional[str] = None, timeout: float = 20.0):
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN") or None
        self.timeout = timeout
        self.requests_made = 0
        self._cache: Dict[str, Any] = {}
        self._lock = threading.Lock()

    @property
    def authenticated(self) -> bool:
        return bool(self.token)

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = path if path.startswith("http") else API_ROOT + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        if url in self._cache:
            return self._cache[url]

        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token

        request = urllib.request.Request(url, headers=headers)
        with self._lock:
            self.requests_made += 1
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise _to_error(exc) from None
        except urllib.error.URLError as exc:
            raise GitHubError("Could not reach GitHub: %s" % exc.reason) from None

        self._cache[url] = data
        return data

    # --- Endpoints -----------------------------------------------------------

    def search_repositories(self, query: str, per_page: int = 20, sort: Optional[str] = None) -> List[dict]:
        params: Dict[str, Any] = {"q": query, "per_page": per_page}
        if sort:
            params["sort"] = sort
        return self.get("/search/repositories", params).get("items", [])

    def search_issues(self, query: str, per_page: int = 30, sort: Optional[str] = None) -> List[dict]:
        params: Dict[str, Any] = {"q": query, "per_page": per_page}
        if sort:
            params["sort"] = sort
            params["order"] = "desc"
        return self.get("/search/issues", params).get("items", [])

    def get_repo(self, repo: str) -> dict:
        return self.get("/repos/%s" % repo)

    def get_issue(self, repo: str, number: int) -> dict:
        return self.get("/repos/%s/issues/%d" % (repo, number))

    def get_timeline(self, repo: str, number: int) -> List[dict]:
        return self.get("/repos/%s/issues/%d/timeline" % (repo, number), {"per_page": 100})

    def recent_closed_pulls(self, repo: str, per_page: int = 50) -> List[dict]:
        params = {"state": "closed", "sort": "updated", "direction": "desc", "per_page": per_page}
        return self.get("/repos/%s/pulls" % repo, params)

    def get_community_profile(self, repo: str) -> dict:
        return self.get("/repos/%s/community/profile" % repo)

    def get_tree(self, repo: str, ref: str) -> List[dict]:
        data = self.get("/repos/%s/git/trees/%s" % (repo, urllib.parse.quote(ref)), {"recursive": "1"})
        return data.get("tree", [])

    def user_repos(self, user: str, per_page: int = 100) -> List[dict]:
        params = {"sort": "pushed", "per_page": per_page, "type": "owner"}
        return self.get("/users/%s/repos" % urllib.parse.quote(user), params)


def _to_error(exc: urllib.error.HTTPError) -> GitHubError:
    try:
        message = json.loads(exc.read().decode("utf-8")).get("message", "")
    except Exception:
        message = ""
    remaining = exc.headers.get("X-RateLimit-Remaining")
    if exc.code in (403, 429) and (remaining == "0" or "rate limit" in message.lower()):
        reset = exc.headers.get("X-RateLimit-Reset")
        wait = ""
        if reset and reset.isdigit():
            wait = " Resets in about %d min." % max(1, (int(reset) - int(time.time())) // 60 + 1)
        return RateLimitError(
            "GitHub rate limit reached.%s Set GITHUB_TOKEN to raise the limit." % wait, exc.code
        )
    return GitHubError("GitHub API error %d: %s" % (exc.code, message or exc.reason), exc.code)


def parse_issue_url(value: str) -> tuple:
    """Accept https://github.com/o/r/issues/12, o/r#12 or o/r/issues/12."""
    text = value.strip()
    for prefix in ("www.github.com/", "github.com/"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    if "#" in text and "://" not in text:
        repo, _, number = text.partition("#")
        if repo.count("/") == 1 and number.isdigit():
            return repo, int(number)
    parsed = urllib.parse.urlparse(text if "://" in text else "https://github.com/" + text)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 4 and parts[2] in ("issues", "pull") and parts[3].isdigit():
        return "%s/%s" % (parts[0], parts[1]), int(parts[3])
    raise ValueError("Not a GitHub issue reference: %r (expected owner/repo#123 or an issue URL)" % value)
