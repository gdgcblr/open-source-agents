"""Shared GitHub REST API client for OSS Pulse Agent.

Provides a thin wrapper around httpx with:
- Optional token-based authentication
- Automatic pagination
- Rate limit awareness
- File content retrieval
- Graceful error handling
"""

from __future__ import annotations

import base64
import os
from typing import Any, Optional

import httpx

GITHUB_API_BASE = "https://api.github.com"
DEFAULT_TIMEOUT = 30.0


class GitHubClientError(Exception):
    """Raised when a GitHub API call fails."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class GitHubClient:
    """Synchronous GitHub REST API client with optional authentication.

    Usage:
        with GitHubClient() as client:
            repo = client.get("/repos/owner/name")
    """

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "OSS-Pulse-Agent/1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        self._client = httpx.Client(
            base_url=GITHUB_API_BASE,
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
            follow_redirects=True,
        )
        self.rate_limit_remaining: Optional[int] = None
        self.is_authenticated: bool = self.token is not None

    def get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        """Make a GET request to the GitHub API.

        Returns None for 404 responses instead of raising an exception,
        since many checks rely on testing whether a resource exists.
        """
        try:
            response = self._client.get(path, params=params)
            self._update_rate_limit(response)

            if response.status_code == 404:
                return None
            if response.status_code == 403 and "rate limit" in response.text.lower():
                raise GitHubClientError(
                    "GitHub API rate limit exceeded. Set GITHUB_TOKEN for higher limits.",
                    status_code=403,
                )
            response.raise_for_status()
            if not response.content:
                return None
            return response.json()
        except httpx.HTTPStatusError as e:
            raise GitHubClientError(
                f"GitHub API error: {e.response.status_code} - {e.response.text[:200]}",
                status_code=e.response.status_code,
            ) from e
        except httpx.RequestError as e:
            raise GitHubClientError(f"Request failed: {e}") from e

    def get_paginated(
        self,
        path: str,
        params: Optional[dict[str, Any]] = None,
        max_pages: int = 5,
    ) -> list[dict[str, Any]]:
        """Fetch paginated results from the GitHub API.

        Follows pagination links up to max_pages, collecting all items.
        """
        params = dict(params or {})
        params.setdefault("per_page", 100)
        all_items: list[dict[str, Any]] = []

        for page in range(1, max_pages + 1):
            params["page"] = page
            try:
                response = self._client.get(path, params=params)
                self._update_rate_limit(response)

                if response.status_code == 404:
                    return []
                response.raise_for_status()

                items = response.json()
                if not isinstance(items, list) or not items:
                    break
                all_items.extend(items)

                # Stop if no more pages
                link_header = response.headers.get("link", "")
                if 'rel="next"' not in link_header:
                    break
            except (httpx.HTTPStatusError, httpx.RequestError):
                break

        return all_items

    def get_file_content(self, owner: str, repo: str, path: str) -> Optional[str]:
        """Get the decoded text content of a file from a repository.

        Returns None if the file doesn't exist or can't be decoded.
        """
        data = self.get(f"/repos/{owner}/{repo}/contents/{path}")
        if data and isinstance(data, dict) and data.get("content"):
            try:
                return base64.b64decode(data["content"]).decode("utf-8")
            except Exception:
                return None
        return None

    def file_exists(self, owner: str, repo: str, path: str) -> bool:
        """Check if a file or directory exists in the repository."""
        data = self.get(f"/repos/{owner}/{repo}/contents/{path}")
        return data is not None

    def dir_listing(self, owner: str, repo: str, path: str) -> list[dict[str, Any]]:
        """List contents of a directory in the repository.

        Returns an empty list if the directory doesn't exist.
        """
        data = self.get(f"/repos/{owner}/{repo}/contents/{path}")
        if isinstance(data, list):
            return data
        return []

    def _update_rate_limit(self, response: httpx.Response) -> None:
        """Track remaining API rate limit from response headers."""
        remaining = response.headers.get("x-ratelimit-remaining")
        if remaining is not None:
            self.rate_limit_remaining = int(remaining)

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
