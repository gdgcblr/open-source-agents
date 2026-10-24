"""GitHub API client for retrieving Pull Request metadata and diffs."""

from __future__ import annotations
import json
import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass


def _get_ssl_context() -> ssl.SSLContext:
    """Create a verified SSL context using certifi on macOS if available."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


@dataclass
class PullRequestMetadata:
    owner: str
    repo: str
    number: int
    title: str
    author: str
    base_branch: str
    head_branch: str
    description: str
    url: str


def parse_pr_identifier(identifier: str) -> tuple[str, str, int]:
    """Parse a GitHub PR URL or string like owner/repo#number into (owner, repo, number)."""
    identifier = identifier.strip()

    # URL format: https://github.com/owner/repo/pull/123
    url_match = re.match(r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)", identifier)
    if url_match:
        return url_match.group(1), url_match.group(2), int(url_match.group(3))

    # Short format: owner/repo#123
    short_match = re.match(r"^([^/]+)/([^#]+)#(\d+)$", identifier)
    if short_match:
        return short_match.group(1), short_match.group(2), int(short_match.group(3))

    raise ValueError(
        f"Invalid GitHub PR identifier: '{identifier}'. "
        "Expected 'https://github.com/owner/repo/pull/123' or 'owner/repo#123'"
    )


class GitHubClient:
    """Client to interact with GitHub REST API."""

    def __init__(self, token: str | None = None):
        self.token = token.strip() if token else None

    def _get_headers(self, accept: str = "application/vnd.github.v3+json") -> dict[str, str]:
        headers = {
            "Accept": accept,
            "User-Agent": "GitHub-PR-Guardian-Agent",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def fetch_pr_metadata(self, owner: str, repo: str, pull_number: int) -> PullRequestMetadata:
        """Fetch PR metadata from GitHub API."""
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}"
        req = urllib.request.Request(url, headers=self._get_headers())

        try:
            with urllib.request.urlopen(req, timeout=15, context=_get_ssl_context()) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return PullRequestMetadata(
                    owner=owner,
                    repo=repo,
                    number=pull_number,
                    title=data.get("title", ""),
                    author=data.get("user", {}).get("login", "unknown"),
                    base_branch=data.get("base", {}).get("ref", ""),
                    head_branch=data.get("head", {}).get("ref", ""),
                    description=data.get("body", "") or "",
                    url=data.get("html_url", url),
                )
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise RuntimeError(f"PR not found or repository is private: {owner}/{repo}#{pull_number}")
            elif e.code == 403:
                raise RuntimeError(
                    f"GitHub API rate limit exceeded or access denied ({e}). "
                    "Consider setting GITHUB_TOKEN in your environment."
                )
            raise RuntimeError(f"GitHub API HTTP error: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to fetch PR metadata: {e}")

    def fetch_pr_diff(self, owner: str, repo: str, pull_number: int) -> str:
        """Fetch unified diff for the PR from GitHub API."""
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}"
        req = urllib.request.Request(
            url,
            headers=self._get_headers(accept="application/vnd.github.v3.diff"),
        )

        try:
            with urllib.request.urlopen(req, timeout=20, context=_get_ssl_context()) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Failed to fetch PR diff ({e.code}): {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to fetch PR diff: {e}")
