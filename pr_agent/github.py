"""Minimal read-only GitHub REST client."""
from __future__ import annotations

import httpx

API = "https://api.github.com"


class GitHub:
    def __init__(self, token: str):
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "pr-agent-local"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.Client(base_url=API, headers=headers, timeout=30)

    def _get(self, path: str, **params) -> httpx.Response:
        r = self._http.get(path, params=params or None)
        if r.status_code == 403 and r.headers.get("x-ratelimit-remaining") == "0":
            raise RuntimeError("GitHub rate limit reached; will retry on the next poll.")
        r.raise_for_status()
        return r

    def open_pulls(self, repo: str) -> list[dict]:
        pulls, page = [], 1
        while True:
            batch = self._get(f"/repos/{repo}/pulls", state="open", per_page=50, page=page,
                              sort="updated", direction="desc").json()
            pulls.extend(batch)
            if len(batch) < 50 or page >= 4:
                return pulls
            page += 1

    def pull(self, repo: str, number: int) -> dict:
        return self._get(f"/repos/{repo}/pulls/{number}").json()

    def pull_files(self, repo: str, number: int) -> list[dict]:
        return self._get(f"/repos/{repo}/pulls/{number}/files", per_page=100).json()

    def pull_diff(self, repo: str, number: int) -> str:
        r = self._http.get(f"/repos/{repo}/pulls/{number}",
                           headers={"Accept": "application/vnd.github.diff"})
        r.raise_for_status()
        return r.text

    def file_content(self, repo: str, path: str, ref: str) -> str | None:
        r = self._http.get(f"/repos/{repo}/contents/{path}", params={"ref": ref},
                           headers={"Accept": "application/vnd.github.raw"})
        return r.text if r.status_code == 200 else None
