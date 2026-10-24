"""Minimal GitHub REST client: fetch a PR with everything the detector needs, and post results."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath

import httpx

from .models import AuthorInfo, ChangedFile, PullRequest

API = "https://api.github.com"
COMMENT_MARKER = "<!-- pr-slop-detector -->"
MANIFEST_NAMES = ("requirements.txt", "pyproject.toml", "package.json", "go.mod", "Cargo.toml")

_PR_REF = re.compile(r"(?:https?://github\.com/)?([\w.-]+)/([\w.-]+)(?:#|/pull/)(\d+)")


def parse_pr_ref(ref: str) -> tuple[str, int]:
    """Accept `owner/repo#123` or `https://github.com/owner/repo/pull/123`."""
    m = _PR_REF.search(ref.strip())
    if not m:
        raise ValueError(f"Could not parse PR reference {ref!r}; use owner/repo#123 or a PR URL.")
    return f"{m.group(1)}/{m.group(2)}", int(m.group(3))


class GitHubClient:
    def __init__(self, token: str | None = None, timeout: float = 20.0):
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.Client(base_url=API, headers=headers, timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def _get(self, path: str, **params):
        r = self._http.get(path, params=params or None)
        r.raise_for_status()
        return r.json()

    def _paginate(self, path: str, limit: int = 300) -> list[dict]:
        items, page = [], 1
        while len(items) < limit:
            batch = self._get(path, per_page=100, page=page)
            items.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return items[:limit]

    # ---------------------------------------------------------------- fetching

    def fetch_pull_request(self, repo: str, number: int, lookback_days: int = 14) -> PullRequest:
        pr = self._get(f"/repos/{repo}/pulls/{number}")
        files = [
            ChangedFile(
                filename=f["filename"],
                status=f.get("status", "modified"),
                additions=f.get("additions", 0),
                deletions=f.get("deletions", 0),
                patch=f.get("patch"),
            )
            for f in self._paginate(f"/repos/{repo}/pulls/{number}/files")
        ]
        commits = [c["commit"]["message"] for c in self._paginate(f"/repos/{repo}/pulls/{number}/commits", 100)]
        author = self._fetch_author(pr["user"]["login"], pr.get("author_association", "NONE"), lookback_days)
        manifests = self._fetch_manifests(repo, pr["head"]["sha"], files)
        local_modules = self._fetch_local_modules(repo, pr["head"]["sha"])
        return PullRequest(
            repo=repo,
            number=number,
            title=pr.get("title") or "",
            body=pr.get("body") or "",
            url=pr.get("html_url"),
            created_at=pr.get("created_at"),
            author=author,
            files=files,
            commit_messages=commits,
            manifests=manifests,
            local_modules=local_modules,
        )

    def _fetch_author(self, login: str, association: str, lookback_days: int) -> AuthorInfo:
        info = AuthorInfo(login=login, association=association)
        try:
            info.account_created_at = self._get(f"/users/{login}").get("created_at")
        except httpx.HTTPError:
            pass
        # Mass drive-by PRs across many unrelated repos is a strong slop-farming signal.
        since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).date().isoformat()
        try:
            res = self._get("/search/issues", q=f"author:{login} type:pr created:>={since}", per_page=100)
            info.recent_pr_count = res.get("total_count", 0)
            info.recent_pr_repo_count = len({i["repository_url"] for i in res.get("items", [])})
        except httpx.HTTPError:
            pass  # search is rate-limited hard for anonymous callers; the signal is optional
        return info

    def _fetch_local_modules(self, repo: str, ref: str) -> list[str]:
        try:
            tree = self._get(f"/repos/{repo}/git/trees/{ref}", recursive=1).get("tree", [])
        except httpx.HTTPError:
            return []
        names = set()
        for entry in tree:
            for part in PurePosixPath(entry["path"]).parts:
                names.add(PurePosixPath(part).stem.lower())
        return sorted(names)

    def _fetch_manifests(self, repo: str, ref: str, files: list[ChangedFile]) -> dict[str, str]:
        """Fetch dependency manifests from the repo root and from each touched project directory."""
        dirs = {""}
        for f in files:
            parts = PurePosixPath(f.filename).parts[:-1]
            for i in range(1, min(len(parts), 3) + 1):  # up to 3 levels deep, e.g. tools/<slug>/
                dirs.add("/".join(parts[:i]))
        found: dict[str, str] = {}
        for d in sorted(dirs):
            for name in MANIFEST_NAMES:
                path = f"{d}/{name}" if d else name
                r = self._http.get(
                    f"/repos/{repo}/contents/{path}",
                    params={"ref": ref},
                    headers={"Accept": "application/vnd.github.raw"},
                )
                if r.status_code == 200:
                    found[path] = r.text
        return found

    # ---------------------------------------------------------------- writing

    def upsert_comment(self, repo: str, number: int, body: str) -> str:
        """Create the report comment, or edit our previous one so re-runs don't spam the thread."""
        body = f"{COMMENT_MARKER}\n{body}"
        for c in self._paginate(f"/repos/{repo}/issues/{number}/comments"):
            if COMMENT_MARKER in (c.get("body") or ""):
                r = self._http.patch(f"/repos/{repo}/issues/comments/{c['id']}", json={"body": body})
                r.raise_for_status()
                return r.json()["html_url"]
        r = self._http.post(f"/repos/{repo}/issues/{number}/comments", json={"body": body})
        r.raise_for_status()
        return r.json()["html_url"]

    def add_label(self, repo: str, number: int, label: str) -> None:
        r = self._http.post(f"/repos/{repo}/issues/{number}/labels", json={"labels": [label]})
        r.raise_for_status()


def pull_request_from_patch(patch_text: str, title: str = "", body: str = "") -> PullRequest:
    """Build a PullRequest from a local `git diff` / `git format-patch` output (offline mode)."""
    files: list[ChangedFile] = []
    current: ChangedFile | None = None
    hunk: list[str] = []

    def flush():
        if current is not None:
            current.patch = "\n".join(hunk) if hunk else None
            files.append(current)

    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            flush()
            m = re.match(r"diff --git a/(.+?) b/(.+)$", line)
            current = ChangedFile(filename=m.group(2) if m else line.split()[-1])
            hunk = []
        elif current is None:
            continue
        elif line.startswith("new file mode"):
            current.status = "added"
        elif line.startswith("deleted file mode"):
            current.status = "removed"
        elif line.startswith(("--- ", "+++ ", "index ", "similarity ", "rename ")):
            continue
        else:
            hunk.append(line)
            if line.startswith("+"):
                current.additions += 1
            elif line.startswith("-"):
                current.deletions += 1
    flush()
    return PullRequest(title=title, body=body, files=files)
