"""Read-only GitHub REST API client.

Only GET requests are made. The issues endpoint also returns pull requests;
those are removed here (records with a "pull_request" field).
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlparse

import requests

from .errors import InvalidInputError, NotFoundError
from .http_client import DEFAULT_TIMEOUT, get_json
from .models import Issue

API = "https://api.github.com"
OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
MAX_PAGES = 3
MAX_LIMIT = 50


@dataclass
class RepoRef:
    owner: str
    repo: str
    issue: int | None = None  # set when the URL pointed at a specific issue

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


def parse_repo(value: str) -> RepoRef:
    """Accept 'owner/repo', 'github.com/owner/repo' or a full GitHub URL
    (optionally ending in /issues/<n>, .git, or a trailing slash)."""
    raw = (value or "").strip()
    if not raw:
        raise InvalidInputError("Repository is empty. Use the form owner/repo, e.g. pallets/flask.")

    path = raw
    if "://" in raw or raw.lower().startswith(("github.com/", "www.github.com/")):
        parsed = urlparse(raw if "://" in raw else "https://" + raw)
        host = (parsed.hostname or "").lower()
        if host not in ("github.com", "www.github.com"):
            raise InvalidInputError(
                f"Only github.com repositories are supported (got host '{host or '?'}')."
            )
        path = parsed.path
    elif raw.startswith("git@github.com:"):
        path = raw.split(":", 1)[1]

    parts = [p for p in path.strip("/").split("/") if p]
    if parts and "." in parts[0] and parts[0].lower() not in ("github.com", "www.github.com"):
        raise InvalidInputError(f"Only github.com repositories are supported (got '{parts[0]}').")
    if len(parts) < 2:
        raise InvalidInputError(f"'{raw}' is not a repository. Use the form owner/repo, e.g. pallets/flask.")
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]

    issue = None
    if len(parts) >= 4 and parts[2] == "issues" and parts[3].isdigit():
        issue = int(parts[3])
    elif len(parts) > 2 and "://" not in raw and not raw.lower().startswith(("github.com/", "www.github.com/")):
        raise InvalidInputError(f"'{raw}' has too many parts. Use the form owner/repo.")

    if not OWNER_RE.match(owner):
        raise InvalidInputError(f"'{owner}' is not a valid GitHub user or organization name.")
    if not REPO_RE.match(repo) or repo in (".", ".."):
        raise InvalidInputError(f"'{repo}' is not a valid GitHub repository name.")
    return RepoRef(owner=owner, repo=repo, issue=issue)


class GitHubClient:
    def __init__(
        self,
        ref: RepoRef,
        *,
        token: str | None = None,
        session: requests.Session | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_pages: int = MAX_PAGES,
    ) -> None:
        self.ref = ref
        self.timeout = timeout
        self.max_pages = max(1, min(max_pages, MAX_PAGES))
        self.session = session or requests.Session()
        self._headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            self._headers["Authorization"] = f"Bearer {token}"
        self.authenticated = bool(token)

    # -- helpers -------------------------------------------------------------
    def _get(self, path: str, *, params: dict[str, Any] | None = None, not_found: str) -> tuple[Any, Any]:
        return get_json(
            self.session,
            f"{API}{path}",
            service="GitHub",
            params=params,
            headers=self._headers,
            timeout=self.timeout,
            not_found=not_found,
        )

    @property
    def _repo_path(self) -> str:
        return f"/repos/{quote(self.ref.owner)}/{quote(self.ref.repo)}"

    def _repo_not_found(self) -> str:
        hint = "" if self.authenticated else " Private repositories need a GITHUB_TOKEN with access."
        return f"Repository {self.ref.full_name} was not found. Check the spelling.{hint}"

    # -- public API ----------------------------------------------------------
    def get_repo(self) -> dict[str, Any]:
        data, _ = self._get(self._repo_path, not_found=self._repo_not_found())
        if not isinstance(data, dict):
            raise NotFoundError(self._repo_not_found())
        return {
            "full_name": data.get("full_name") or self.ref.full_name,
            "html_url": data.get("html_url") or f"https://github.com/{self.ref.full_name}",
            "description": data.get("description") or "",
            "language": data.get("language") or "",
            "default_branch": data.get("default_branch") or "",
            "archived": bool(data.get("archived")),
            "has_issues": data.get("has_issues", True),
            "open_issues_count": data.get("open_issues_count", 0),
        }

    def list_issues(self, *, labels: list[str] | None = None, limit: int = 20) -> tuple[list[Issue], int]:
        """Return up to `limit` open issues (pull requests removed) and the number of PRs removed.

        At most MAX_PAGES pages are fetched, so very busy repositories are sampled
        (most recently updated first), never fully scanned.
        """
        limit = max(1, min(limit, MAX_LIMIT))
        params: dict[str, Any] = {
            "state": "open",
            "sort": "updated",
            "direction": "desc",
            "per_page": min(100, max(30, limit * 2)),
        }
        if labels:
            params["labels"] = ",".join(labels)

        issues: list[Issue] = []
        excluded = 0
        for page in range(1, self.max_pages + 1):
            params["page"] = page
            data, resp = self._get(f"{self._repo_path}/issues", params=params, not_found=self._repo_not_found())
            if not isinstance(data, list):
                break
            for raw in data:
                if not isinstance(raw, dict):
                    continue
                if "pull_request" in raw:
                    excluded += 1
                    continue
                issues.append(self._to_issue(raw))
                if len(issues) >= limit:
                    return issues, excluded
            if len(data) < params["per_page"] or "next" not in getattr(resp, "links", {}):
                break
        return issues, excluded

    def get_issue(self, number: int) -> Issue:
        data, _ = self._get(
            f"{self._repo_path}/issues/{int(number)}",
            not_found=f"Issue #{number} was not found in {self.ref.full_name}.",
        )
        if not isinstance(data, dict):
            raise NotFoundError(f"Issue #{number} was not found in {self.ref.full_name}.")
        if "pull_request" in data:
            raise InvalidInputError(f"#{number} in {self.ref.full_name} is a pull request, not an issue.")
        return self._to_issue(data)

    def list_comments(self, number: int, *, max_comments: int = 10) -> list[dict[str, str]]:
        data, _ = self._get(
            f"{self._repo_path}/issues/{int(number)}/comments",
            params={"per_page": max(1, min(max_comments, 30))},
            not_found=f"Issue #{number} was not found in {self.ref.full_name}.",
        )
        out = []
        for c in data if isinstance(data, list) else []:
            if isinstance(c, dict):
                out.append({
                    "author": ((c.get("user") or {}).get("login") or "unknown"),
                    "author_association": c.get("author_association") or "",
                    "created_at": c.get("created_at") or "",
                    "body": c.get("body") or "",
                })
        return out

    def list_dir(self, path: str = "") -> list[dict[str, str]]:
        path = path.strip("/")
        data, _ = self._get(
            f"{self._repo_path}/contents/{quote(path)}" if path else f"{self._repo_path}/contents",
            not_found=f"Path '{path or '/'}' was not found in {self.ref.full_name}.",
        )
        if isinstance(data, dict):  # a single file
            data = [data]
        return [
            {"name": e.get("name", ""), "path": e.get("path", ""), "type": e.get("type", "")}
            for e in (data if isinstance(data, list) else [])[:100]
            if isinstance(e, dict)
        ]

    def read_file(self, path: str, *, max_chars: int = 8000) -> str:
        path = path.strip("/")
        data, _ = self._get(
            f"{self._repo_path}/contents/{quote(path)}",
            not_found=f"File '{path}' was not found in {self.ref.full_name}.",
        )
        if not isinstance(data, dict) or data.get("type") != "file":
            raise InvalidInputError(f"'{path}' is not a file.")
        content = data.get("content")
        if not content or data.get("encoding") != "base64":
            raise InvalidInputError(f"'{path}' is too large or has no readable content.")
        raw = base64.b64decode(content)
        if b"\x00" in raw[:2000]:
            raise InvalidInputError(f"'{path}' looks like a binary file.")
        text = raw.decode("utf-8", errors="replace")
        return text[:max_chars] + (f"\n[... truncated at {max_chars} characters]" if len(text) > max_chars else "")

    # -- normalization --------------------------------------------------------
    @staticmethod
    def _to_issue(raw: dict[str, Any]) -> Issue:
        number = raw.get("number")
        return Issue(
            source="github",
            id=str(number),
            display_id=f"#{number}",
            title=(raw.get("title") or "(no title)").strip(),
            url=raw.get("html_url") or "",
            body=raw.get("body") or "",
            labels=[
                (lbl.get("name") if isinstance(lbl, dict) else str(lbl)) or ""
                for lbl in (raw.get("labels") or [])
            ],
            state=raw.get("state") or "open",
            assignees=[a.get("login", "") for a in (raw.get("assignees") or []) if isinstance(a, dict)],
            comments=int(raw.get("comments") or 0),
            created_at=raw.get("created_at") or "",
            updated_at=raw.get("updated_at") or "",
            locked=bool(raw.get("locked")),
        )
