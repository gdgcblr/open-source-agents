"""Where submissions come from: PRs of a GitHub repo (via git + one REST listing) or local folders.

PR code is fetched with plain git (`refs/pull/*/head`), which needs no API quota and gives us every
commit, so secret scanning covers keys that were committed and later deleted. Nothing is executed:
trees are extracted with tarfile's "data" filter, which rejects absolute paths and escaping links.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import shutil
import subprocess
import tarfile
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import httpx

from judge.models import SubmissionMeta
from judge.workspace import AddedLine, Workspace, list_local_files

log = logging.getLogger(__name__)

PROJECT_RE = re.compile(r"^(agents|tools)/([^/.][^/]*)/")  # dot-folders (agents/.github) are not projects
INDEX_FILES = {"agents/README.md", "tools/README.md"}
MAX_HISTORY_LINES = 200_000


class SourceError(RuntimeError):
    pass


def _git(repo: Path, *args: str, binary: bool = False, check: bool = True) -> str | bytes:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    if check and proc.returncode != 0:
        raise SourceError(f"git {' '.join(args[:3])}… failed: {proc.stderr.decode(errors='replace').strip()}")
    return proc.stdout if binary else proc.stdout.decode("utf-8", errors="replace")


def body_hash(body: str) -> str:
    return hashlib.sha256((body or "").encode()).hexdigest()[:16]


class GitHubRepoSource:
    """Mirror of a GitHub repo plus PR metadata from the REST API."""

    def __init__(self, repo: str, cache_dir: Path, token: str | None = None):
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
            raise SourceError(f"expected owner/name, got {repo!r}")
        self.repo = repo
        self.token = token
        self.mirror = cache_dir / "repos" / (repo.replace("/", "__") + ".git")
        self.work_root = cache_dir / "workspaces"

    # ----- git mirror ------------------------------------------------------------------------
    def sync(self) -> None:
        url = f"https://github.com/{self.repo}.git"
        if not self.mirror.exists():
            self.mirror.parent.mkdir(parents=True, exist_ok=True)
            log.info("cloning %s", url)
            subprocess.run(["git", "clone", "--bare", "--quiet", url, str(self.mirror)], check=True)
        log.info("fetching PR refs for %s", self.repo)
        _git(
            self.mirror,
            "fetch",
            "--quiet",
            "--prune",
            "--force",
            "origin",
            "+refs/heads/*:refs/heads/*",
            "+refs/pull/*/head:refs/pull/*/head",
        )

    def default_branch(self) -> str:
        head = str(_git(self.mirror, "symbolic-ref", "--short", "HEAD", check=False)).strip()
        return head or "main"

    def pr_numbers_from_git(self) -> list[int]:
        refs = str(_git(self.mirror, "for-each-ref", "--format=%(refname)", "refs/pull/"))
        nums = {int(m.group(1)) for m in re.finditer(r"refs/pull/(\d+)/head", refs)}
        return sorted(nums)

    def resolve(self, rev: str) -> str | None:
        out = str(_git(self.mirror, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}", check=False)).strip()
        return out or None

    # ----- REST metadata ---------------------------------------------------------------------
    def list_prs(self, state: str = "all") -> list[SubmissionMeta]:
        """PR metadata from the REST API.

        Uses ETag conditional requests (a 304 doesn't count against GitHub's rate limit) and falls back
        to the last cached listing, then to bare git refs marked `partial`, when the API is unavailable."""
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        cache_file = self.mirror.parent.parent / "meta" / f"{self.repo.replace('/', '__')}-{state}.json"
        try:
            cache = json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cache = {"pages": {}}
        prs: list[dict] = []
        try:
            with httpx.Client(timeout=30, headers=headers) as client:
                page = 1
                while True:
                    cached = cache["pages"].get(str(page), {})
                    extra = {"If-None-Match": cached["etag"]} if cached.get("etag") else {}
                    r = client.get(
                        f"https://api.github.com/repos/{self.repo}/pulls",
                        params={"state": state, "per_page": 100, "page": page},
                        headers=extra,
                    )
                    if r.status_code == 304:
                        batch = cached["data"]
                    else:
                        r.raise_for_status()
                        batch = r.json()
                        cache["pages"][str(page)] = {"etag": r.headers.get("etag"), "data": batch}
                    prs.extend(batch)
                    if len(batch) < 100:
                        break
                    page += 1
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(cache), encoding="utf-8")
        except httpx.HTTPError as exc:
            prs = [pr for p in sorted(cache["pages"], key=int) for pr in cache["pages"][p]["data"]]
            log.warning(
                "GitHub API unavailable (%s); using %s",
                exc,
                f"cached listing of {len(prs)} PRs" if prs else "git refs only",
            )
        metas = {pr["number"]: self._meta(pr) for pr in prs}
        for n in self.pr_numbers_from_git():  # PRs newer than the cached listing
            if n not in metas and (state == "all" or not prs):
                metas[n] = SubmissionMeta(
                    id=str(n),
                    number=n,
                    title=f"PR #{n}",
                    partial=True,
                    head_sha=self.resolve(f"refs/pull/{n}/head") or "",
                    url=f"https://github.com/{self.repo}/pull/{n}",
                )
        for m in metas.values():  # the git mirror is fresher than a cached listing for head commits
            git_head = self.resolve(f"refs/pull/{m.number}/head")
            if git_head and m.state == "open":
                m.head_sha = git_head
        return sorted(metas.values(), key=lambda m: m.number or 0)

    @staticmethod
    def _meta(pr: dict) -> SubmissionMeta:
        state = "merged" if pr.get("merged_at") else pr.get("state", "open")
        user = pr.get("user") or {}
        return SubmissionMeta(
            id=str(pr["number"]),
            number=pr["number"],
            title=pr.get("title") or "",
            url=pr.get("html_url"),
            author=user.get("login"),
            author_avatar=user.get("avatar_url"),
            state=state,
            created_at=pr.get("created_at"),
            updated_at=pr.get("updated_at"),
            head_sha=(pr.get("head") or {}).get("sha", ""),
            head_ref=(pr.get("head") or {}).get("ref"),
            base_sha=(pr.get("base") or {}).get("sha"),
            body=pr.get("body") or "",
        )

    # ----- workspace -------------------------------------------------------------------------
    def workspace(self, meta: SubmissionMeta) -> Workspace:
        head = self.resolve(meta.head_sha) if meta.head_sha else None
        head = head or self.resolve(f"refs/pull/{meta.number}/head")
        if not head:
            raise SourceError(f"PR #{meta.number}: head commit not found")
        meta.head_sha = head
        base = None
        for candidate in (meta.base_sha, f"refs/heads/{self.default_branch()}"):
            if candidate and self.resolve(candidate):
                mb = str(_git(self.mirror, "merge-base", candidate, head, check=False)).strip()
                # For merged PRs the head is already in main, so merge-base(main, head) == head.
                if mb and mb != head:
                    base = mb
                    break
        if base is None:
            raise SourceError(f"PR #{meta.number}: could not determine base commit")

        changed: dict[str, int] = {}
        for line in str(_git(self.mirror, "diff", "--numstat", "--no-renames", base, head)).splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                added, deleted, path = parts
                changed[path] = (int(added) if added.isdigit() else 0) + (int(deleted) if deleted.isdigit() else 0)

        folders = project_folders(list(changed))
        project_path = folders[0] if folders else ""
        # Extra folders the PR *creates* belong to this submission (agent + its MCP server, say);
        # folders that already existed on the base branch are someone else's project.
        extra = [f for f in folders[1:] if not self._exists_at(base, f)]
        foreign = [f for f in folders[1:] if f not in extra]
        if project_path and self._exists_at(base, project_path):
            log.info("PR #%s updates existing folder %s", meta.number, project_path)
        dest = self.work_root / meta.id
        files: list[str] = []
        if project_path:
            self._extract(head, [project_path, *extra], dest)
            files = list_local_files(dest / project_path)
            for f in extra:
                files += [f"/{f}/{rel}" for rel in list_local_files(dest / f)]
        commits = str(_git(self.mirror, "log", "--format=%s", f"{base}..{head}")).splitlines()
        return Workspace(
            root=dest / project_path if project_path else dest,
            project_path=project_path,
            files=files,
            meta=meta,
            changed_paths=sorted(changed),
            changed_lines=changed,
            history=list(self._added_lines(base, head)),
            commit_messages=commits,
            extra_projects=extra,
            foreign_projects=foreign,
            repo_root=dest,
        )

    def _exists_at(self, rev: str, path: str) -> bool:
        proc = subprocess.run(
            ["git", "-C", str(self.mirror), "cat-file", "-e", f"{rev}:{path}"], capture_output=True, check=False
        )
        return proc.returncode == 0

    def _extract(self, rev: str, paths: list[str], dest: Path) -> None:
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        data = _git(self.mirror, "archive", "--format=tar", rev, *paths, binary=True)
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:  # type: ignore[arg-type]
            tar.extractall(dest, filter="data")

    def _added_lines(self, base: str, head: str) -> Iterator[AddedLine]:
        out = str(
            _git(
                self.mirror,
                "log",
                "-p",
                "--no-color",
                "--unified=0",
                "--no-renames",
                "--format=%x00%H",
                f"{base}..{head}",
            )
        )
        commit, path, line_no, count = "", "", 0, 0
        for raw in out.splitlines():
            if raw.startswith("\x00"):
                commit = raw[1:].strip()
            elif raw.startswith("+++ "):
                path = raw[6:] if raw.startswith("+++ b/") else ""
            elif raw.startswith("@@"):
                m = re.search(r"\+(\d+)", raw)
                line_no = int(m.group(1)) if m else 0
            elif raw.startswith("+") and path:
                yield AddedLine(commit=commit, path=path, line=line_no, text=raw[1:])
                line_no += 1
                count += 1
                if count >= MAX_HISTORY_LINES:
                    log.warning("history scan truncated at %d lines", MAX_HISTORY_LINES)
                    return


def project_folders(changed: list[str]) -> list[str]:
    """agents/<slug> and tools/<slug> folders touched by the PR, most-changed first."""
    counts = Counter(m.group(0).rstrip("/") for p in changed if (m := PROJECT_RE.match(p)))
    return [folder for folder, _ in counts.most_common()]


def local_workspace(folder: Path) -> Workspace:
    """Judge a folder on disk (self-judging, tests, pre-PR checks). Scope is assumed clean."""
    folder = folder.resolve()
    if not folder.is_dir():
        raise SourceError(f"{folder} is not a directory")
    parts = folder.parts
    project_path = folder.name
    for i in range(len(parts) - 1, 0, -1):
        if parts[i - 1] in ("agents", "tools"):
            project_path = f"{parts[i - 1]}/{parts[i]}"
            break
    files = _git_visible_files(folder) or list_local_files(folder)
    meta = SubmissionMeta(id=f"local-{folder.name}", title=folder.name, state="local")
    return Workspace(
        root=folder,
        project_path=project_path,
        files=files,
        meta=meta,
        changed_paths=[f"{project_path}/{f}" for f in files],
        changed_lines={},
    )


def _git_visible_files(folder: Path) -> list[str]:
    """Tracked + untracked-but-not-ignored files, i.e. what a commit of this folder would contain."""
    proc = subprocess.run(
        ["git", "-C", str(folder), "ls-files", "--cached", "--others", "--exclude-standard", "--full-name", "."],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    top = subprocess.run(
        ["git", "-C", str(folder), "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False
    ).stdout.strip()
    prefix = folder.relative_to(Path(top).resolve()).as_posix() + "/" if top else ""
    out = []
    for f in proc.stdout.splitlines():
        rel = f[len(prefix) :] if prefix and f.startswith(prefix) else f
        if (folder / rel).is_file():
            out.append(rel)
    return sorted(set(out))
