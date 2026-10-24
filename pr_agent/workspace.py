"""Isolated local workspaces via git worktrees. Nothing here pushes or publishes."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .config import Config, RepoConfig


def git(args: list[str], cwd: Path, check: bool = True, timeout: int = 300) -> str:
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {(p.stderr or p.stdout).strip()[-800:]}")
    return p.stdout


def _slug(repo: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "__", repo)


def ensure_clone(cfg: Config, repo: RepoConfig) -> Path:
    base = cfg.workspace_dir / _slug(repo.name)
    clone = base / "repo"
    if not (clone / ".git").exists():
        base.mkdir(parents=True, exist_ok=True)
        url = repo.clone_url or f"git@github.com:{repo.name}.git"
        git(["clone", "--no-checkout", url, str(clone)], cwd=base, timeout=900)
    # Pushing is disabled at the git level as a second line of defence.
    git(["remote", "set-url", "--push", "origin", "DISABLED_BY_PR_AGENT"], cwd=clone)
    git(["fetch", "--prune", "origin"], cwd=clone, timeout=900)
    return clone


def create_worktree(cfg: Config, repo: RepoConfig, number: int, sha: str, base_ref: str) -> tuple[Path, str]:
    """Create a fresh worktree on the base branch. Returns (path, base_commit)."""
    clone = ensure_clone(cfg, repo)
    git(["fetch", "origin", f"+pull/{number}/head:refs/remotes/origin/pr/{number}"], cwd=clone, timeout=900)
    head = git(["rev-parse", f"refs/remotes/origin/pr/{number}"], cwd=clone).strip()
    if head != sha:
        raise RuntimeError(f"PR head moved to {head[:7]} (approved {sha[:7]}). Re-evaluate before implementing.")
    base_commit = git(["rev-parse", f"origin/{repo.base_branch or base_ref}"], cwd=clone).strip()
    wt = cfg.workspace_dir / _slug(repo.name) / "worktrees" / f"pr-{number}-{sha[:7]}"
    branch = f"pr-agent/pr-{number}-{sha[:7]}"
    if wt.exists():
        git(["worktree", "remove", "--force", str(wt)], cwd=clone, check=False)
    git(["worktree", "prune"], cwd=clone)
    git(["branch", "-D", branch], cwd=clone, check=False)
    git(["worktree", "add", "-b", branch, str(wt), base_commit], cwd=clone)
    return wt, base_commit


def pr_patch(cfg: Config, repo: RepoConfig, number: int, base_commit: str) -> str:
    clone = cfg.workspace_dir / _slug(repo.name) / "repo"
    merge_base = git(["merge-base", base_commit, f"refs/remotes/origin/pr/{number}"], cwd=clone).strip()
    return git(["diff", merge_base, f"refs/remotes/origin/pr/{number}"], cwd=clone)


def changed_files(wt: Path) -> list[dict]:
    out = git(["status", "--porcelain", "--untracked-files=all"], cwd=wt)
    return [{"status": line[:2].strip(), "path": line[3:]} for line in out.splitlines() if line.strip()]


def diff_text(wt: Path, limit: int = 60000) -> str:
    git(["add", "-N", "."], cwd=wt, check=False)  # include new files in the diff without staging content
    return git(["diff"], cwd=wt)[:limit]


def detect_checks(wt: Path) -> list[str]:
    """Pick sensible validation commands when the repo config does not list any."""
    checks: list[str] = []
    if any((wt / f).exists() for f in ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")) \
            or any(wt.glob("*.py")):
        checks.append("python -m compileall -q .")
        if (wt / "tests").is_dir() or any(wt.rglob("test_*.py")):
            checks.append("python -m pytest -q")
    pkg = wt / "package.json"
    if pkg.exists():
        import json
        scripts = (json.loads(pkg.read_text(encoding="utf-8") or "{}").get("scripts") or {})
        for s in ("lint", "typecheck", "build"):
            if s in scripts:
                checks.append(f"npm run {s}")
        if "test" in scripts:
            checks.append("npm test")
    if (wt / "go.mod").exists():
        checks += ["go vet ./...", "go test ./..."]
    if (wt / "Cargo.toml").exists():
        checks.append("cargo test")
    return checks
