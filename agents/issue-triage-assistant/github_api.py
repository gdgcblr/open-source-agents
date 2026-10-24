"""Read-only helpers for fetching public GitHub issues and repository labels."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class GitHubAPIError(RuntimeError):
    """A GitHub URL, API, or response error that can be shown to a user."""


def parse_issue_url(issue_url: str) -> tuple[str, str, int]:
    """Return owner, repository, and issue number for a public github.com issue URL."""
    parsed = urlparse(issue_url.strip())
    parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or len(parts) != 4
        or parts[2] != "issues"
        or not re.fullmatch(r"[1-9][0-9]*", parts[3])
    ):
        raise GitHubAPIError("Enter a public issue URL like https://github.com/owner/repo/issues/123")
    return parts[0], parts[1], int(parts[3])


def _get_json(url: str, timeout: int = 15) -> Any:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "issue-triage-assistant",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 404:
            detail = "Issue or repository not found. Check that the URL is public and correct."
        elif exc.code in {403, 429}:
            detail = "GitHub rate-limited this request. Wait a while and try again."
        else:
            detail = f"GitHub returned HTTP {exc.code}."
        raise GitHubAPIError(detail) from exc
    except (URLError, TimeoutError) as exc:
        raise GitHubAPIError(f"Could not reach the GitHub API: {exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GitHubAPIError("GitHub returned an unreadable response.") from exc


def fetch_public_issue(issue_url: str, timeout: int = 15) -> dict[str, Any]:
    """Fetch a public GitHub issue. Pull requests are rejected even though GitHub's API shares the endpoint."""
    owner, repo, number = parse_issue_url(issue_url)
    data = _get_json(
        f"https://api.github.com/repos/{owner}/{repo}/issues/{number}",
        timeout=timeout,
    )
    if not isinstance(data, dict):
        raise GitHubAPIError("GitHub returned an unexpected issue response.")
    if "pull_request" in data:
        raise GitHubAPIError("That URL is a pull request. Enter an issue URL instead.")
    title, body = data.get("title"), data.get("body") or ""
    if not isinstance(title, str) or not isinstance(body, str):
        raise GitHubAPIError("GitHub returned an issue without a readable title or description.")
    return {
        "owner": owner,
        "repo": repo,
        "number": number,
        "title": title,
        "body": body,
        "state": data.get("state", "unknown"),
        "url": data.get("html_url", issue_url),
    }


def fetch_repository_labels(owner: str, repo: str, timeout: int = 15) -> list[str]:
    """Fetch repository labels, following pages when there are more than 100."""
    labels: list[str] = []
    for page in range(1, 11):
        data = _get_json(
            f"https://api.github.com/repos/{owner}/{repo}/labels?per_page=100&page={page}",
            timeout=timeout,
        )
        if not isinstance(data, list):
            raise GitHubAPIError("GitHub returned an unexpected repository-label response.")
        labels.extend(
            item["name"]
            for item in data
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        )
        if len(data) < 100:
            break
    return labels
