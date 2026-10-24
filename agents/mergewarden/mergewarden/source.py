"""Turn a PR URL or a local checkout into a read-only Submission snapshot.

PR code is never executed here. We copy the PR head's blobs out of git into a
temp folder and read files from it. We deliberately don't use `git archive`,
because it honours the PR's own `.gitattributes` (`export-ignore` would let a PR
hide files from every check). The policy is extracted from the *base* branch.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

from .checks.scope import project_dirs
from .models import Submission
from .policy import Policy, compile_policy

CACHE = Path(os.environ.get("GATEKEEPER_CACHE", Path.home() / ".cache" / "mergewarden"))
PR_RX = re.compile(r"(?:https?://github\.com/)?([\w.-]+)/([\w.-]+)(?:/pull/|#)(\d+)")
# Base-branch paths we snapshot: the rules plus existing projects (for overlap checks).
POLICY_PATHS = ["CONTRIBUTING.md", "README.md", "template", ".github", "agents", "tools"]


def _git(*args: str, cwd: Path | None = None, binary: bool = False):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.decode(errors='replace').strip()}")
    return r.stdout if binary else r.stdout.decode()


HISTORY_CAP = 5_000_000  # bytes of `git log -p` we are willing to scan


def _extract(repo: Path, ref: str, dest: Path, paths: Optional[list[str]] = None) -> list[str]:
    """Write every regular file of the tree at `ref` into `dest`, read straight
    from the object store: no checkout, no hooks, no filters, no attributes.

    Symlinks are skipped (they could point outside `dest`), and so is any path
    that is absolute or contains `..`. Returns the submodule gitlinks found, since
    their code is never in the snapshot.
    """
    listing = _git("ls-tree", "-r", "-z", "--full-tree", ref, "--", *(paths or []), cwd=repo, binary=True)
    blobs: list[tuple[str, str]] = []
    gitlinks: list[str] = []
    for rec in listing.split(b"\0"):
        if not rec:
            continue
        meta, raw_path = rec.split(b"\t", 1)
        mode, kind, sha = meta.split()
        path = raw_path.decode("utf-8", "replace")
        if mode == b"160000":
            gitlinks.append(path)
            continue
        parts = path.split("/")
        if kind != b"blob" or mode == b"120000" or path.startswith("/") or ".." in parts or "" in parts:
            continue
        blobs.append((sha.decode(), path))
    if not blobs:
        return gitlinks
    req = "".join(sha + "\n" for sha, _ in blobs).encode()
    r = subprocess.run(["git", "cat-file", "--batch"], cwd=repo, input=req, capture_output=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"git cat-file failed: {r.stderr.decode(errors='replace').strip()}")
    data, pos = r.stdout, 0
    root = dest.resolve()
    for sha, path in blobs:
        nl = data.index(b"\n", pos)
        header = data[pos:nl].split()
        if len(header) < 3 or header[1] != b"blob":  # "<sha> missing"
            pos = nl + 1
            continue
        size = int(header[2])
        content = data[nl + 1: nl + 1 + size]
        pos = nl + 1 + size + 1  # content is followed by a newline
        target = (dest / path).resolve()
        if root not in target.parents:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return gitlinks


def _history(repo: Path, rev_range: str) -> tuple[Optional[list[tuple[str, str, str]]], Optional[str]]:
    """Every line added in `rev_range`, so secrets committed then deleted are still found."""
    try:
        r = subprocess.run(["git", "log", "-p", "--no-color", "--no-ext-diff", "--no-textconv", "--format=commit %H",
                            rev_range], cwd=repo, capture_output=True, timeout=300)
    except subprocess.TimeoutExpired:
        return None, "history scan timed out"
    if r.returncode != 0:
        return None, "history scan failed: " + r.stderr.decode(errors="replace").strip()[:200]
    raw = r.stdout
    note = None
    if len(raw) > HISTORY_CAP:
        raw, note = raw[:HISTORY_CAP], f"history scan truncated at {HISTORY_CAP // 1_000_000} MB"
    added: list[tuple[str, str, str]] = []
    commit, path = "", ""
    for line in raw.decode("utf-8", "replace").splitlines():
        if line.startswith("commit "):
            commit = line[7:].strip()
        elif line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("+") and not line.startswith("+++"):
            added.append((commit, path, line[1:]))
    return added, note


def github_api(path: str) -> dict:
    """GET from the GitHub REST API. Uses GITHUB_TOKEN or the gh CLI login if present."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token and shutil.which("gh"):
        r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
        token = r.stdout.strip() if r.returncode == 0 else None
    req = urllib.request.Request(f"https://api.github.com/{path.lstrip('/')}",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "mergewarden"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _mirror(owner: str, repo: str) -> Path:
    path = CACHE / f"{owner}__{repo}.git"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        _git("clone", "--bare", "--filter=blob:none", "--quiet", f"https://github.com/{owner}/{repo}.git", str(path))
    return path


def load_pr(ref: str, workdir: Path) -> tuple[Submission, Policy]:
    m = PR_RX.search(ref)
    if not m:
        raise ValueError(f"Not a PR reference: {ref!r} (expected https://github.com/OWNER/REPO/pull/N)")
    owner, repo, num = m.group(1), m.group(2), int(m.group(3))
    meta = github_api(f"repos/{owner}/{repo}/pulls/{num}")
    base_ref = meta["base"]["ref"]
    mirror = _mirror(owner, repo)
    _git("fetch", "--quiet", "--force", "origin",
         f"+refs/heads/{base_ref}:refs/gatekeeper/base",
         f"+refs/pull/{num}/head:refs/gatekeeper/pr-{num}", cwd=mirror)
    head = f"refs/gatekeeper/pr-{num}"
    merge_base = _git("merge-base", "refs/gatekeeper/base", head, cwd=mirror).strip()
    changed = _git("diff", "--name-only", f"{merge_base}..{head}", cwd=mirror).split("\n")

    base_dir, head_dir = workdir / "base", workdir / "head"
    base_dir.mkdir(parents=True)
    head_dir.mkdir(parents=True)
    _extract(mirror, "refs/gatekeeper/base", base_dir, POLICY_PATHS)
    gitlinks = _extract(mirror, head, head_dir)
    history, note = _history(mirror, f"{merge_base}..{head}")
    policy = compile_policy(base_dir)
    changed = [c for c in changed if c]
    dirs = project_dirs(changed, policy)
    sub = Submission(
        root=head_dir, project_dir=dirs[0] if dirs else None, changed_files=changed,
        title=meta.get("title") or "", body=meta.get("body") or "", url=meta["html_url"],
        author=(meta.get("user") or {}).get("login"), number=num, base_root=base_dir,
        gitlinks=gitlinks, history_added=history, history_note=note,
    )
    return sub, policy


def _base_ref(repo: Path) -> str:
    for ref in ("upstream/main", "origin/main", "main", "upstream/master", "origin/master", "master"):
        r = subprocess.run(["git", "rev-parse", "--verify", "--quiet", ref], cwd=repo, capture_output=True)
        if r.returncode == 0:
            return ref
    raise RuntimeError("Could not find a base branch (tried upstream/main, origin/main, main).")


def load_local(path: str, workdir: Path, project: Optional[str] = None) -> tuple[Submission, Policy]:
    """Pre-flight a contribution in a local clone before opening the PR."""
    p = Path(path).resolve()
    root = Path(_git("rev-parse", "--show-toplevel", cwd=p if p.is_dir() else p.parent).strip())
    base = _base_ref(root)
    merge_base = _git("merge-base", base, "HEAD", cwd=root).strip()
    changed = set(_git("diff", "--name-only", merge_base, cwd=root).split("\n"))
    tracked = set(_git("ls-files", "--cached", "--others", "--exclude-standard", cwd=root).split("\n"))
    untracked = set(_git("ls-files", "--others", "--exclude-standard", cwd=root).split("\n"))
    changed = sorted(c for c in changed | untracked if c)

    base_dir = workdir / "base"
    base_dir.mkdir(parents=True)
    _extract(root, base, base_dir, POLICY_PATHS)
    policy = compile_policy(base_dir)
    if not project and p != root:
        rel = p.relative_to(root).parts
        if len(rel) >= 2 and rel[0] in policy.project_roots:
            project = "/".join(rel[:2])
    dirs = project_dirs(changed, policy)
    history, note = _history(root, f"{merge_base}..HEAD")
    gitlinks = [line.split("\t", 1)[1] for line in _git("ls-files", "-s", cwd=root).splitlines()
                if line.startswith("160000 ")]
    sub = Submission(root=root, project_dir=project or (dirs[0] if dirs else None),
                     changed_files=changed, tracked=tracked - {""}, base_root=base_dir,
                     gitlinks=gitlinks, history_added=history, history_note=note)
    return sub, policy


def load(target: str, project: Optional[str] = None) -> tuple[Submission, Policy, Path]:
    """Returns (submission, policy, workdir). Caller removes workdir when done."""
    workdir = Path(tempfile.mkdtemp(prefix="gatekeeper-"))
    try:
        if PR_RX.search(target) and not Path(target).exists():
            sub, pol = load_pr(target, workdir)
        else:
            sub, pol = load_local(target, workdir, project)
    except Exception:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    return sub, pol, workdir
