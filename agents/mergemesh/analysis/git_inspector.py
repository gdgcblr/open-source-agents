"""Safe Git repository and revision inspector for analyzing local repositories."""

from __future__ import annotations

import subprocess
from pathlib import Path, PurePosixPath

from analysis.contract_extractor import ContractAnalysisError, parse_contract_content


class RepoInspectionError(ValueError):
    """Raised when a local repository path, Git revision, or file path is invalid."""


def _run_git_cmd(repo_path: Path, args: list[str], timeout_sec: int = 10) -> subprocess.CompletedProcess[str]:
    """Run a read-only Git command with shell=False in the specified repository directory."""
    cmd = ["git", *args]
    try:
        return subprocess.run(
            cmd,
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            shell=False,
        )
    except OSError as exc:
        raise RepoInspectionError(f"Failed to execute git command in {repo_path}: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RepoInspectionError(f"Git command timed out after {timeout_sec}s in {repo_path}") from exc


def validate_git_repository(repo_path: str | Path) -> Path:
    """Validate that repo_path exists and is a Git working tree."""
    if not repo_path or not str(repo_path).strip():
        raise RepoInspectionError("Repository path cannot be empty.")

    resolved = Path(str(repo_path).strip()).resolve()
    if not resolved.exists():
        raise RepoInspectionError(f"Repository path does not exist: {resolved}")
    if not resolved.is_dir():
        raise RepoInspectionError(f"Repository path is not a directory: {resolved}")

    res = _run_git_cmd(resolved, ["rev-parse", "--is-inside-work-tree"])
    if res.returncode != 0 or res.stdout.strip().lower() != "true":
        raise RepoInspectionError(
            f"Directory '{resolved}' is not a valid Git repository: {(res.stderr or '').strip()}"
        )
    return resolved


def validate_git_revision(repo_path: Path, ref: str) -> str:
    """Validate a Git revision (commit, branch, tag, or 'WORKTREE') and return its resolved commit SHA or 'WORKTREE'."""
    cleaned = (ref or "").strip()
    if not cleaned:
        raise RepoInspectionError(f"Git revision cannot be empty for repository '{repo_path.name}'.")
    if cleaned.startswith("-"):
        raise RepoInspectionError(f"Invalid Git revision '{cleaned}': cannot start with '-'.")
    if cleaned.upper() == "WORKTREE":
        return "WORKTREE"

    res = _run_git_cmd(repo_path, ["rev-parse", "--verify", f"{cleaned}^{{commit}}"])
    if res.returncode != 0:
        raise RepoInspectionError(
            f"Invalid or unavailable Git revision '{cleaned}' in repository '{repo_path.name}': "
            f"{(res.stderr or '').strip() or 'revision not found'}"
        )
    return res.stdout.strip()


def _sanitize_rel_path(rel_path: str) -> str:
    """Normalize a repository-relative path to POSIX format and reject path traversal."""
    cleaned = (rel_path or "").strip().replace("\\", "/").lstrip("/")
    if not cleaned:
        raise RepoInspectionError("Repository relative file path cannot be empty.")
    posix = PurePosixPath(cleaned)
    if ".." in posix.parts or posix.is_absolute():
        raise RepoInspectionError(f"Relative path '{rel_path}' cannot traverse outside the repository.")
    return str(posix)


def read_repo_file_at_revision(repo_path: Path, ref: str, rel_path: str) -> str:
    """Read a file's contents from a Git repository at a validated revision or 'WORKTREE'."""
    safe_rel = _sanitize_rel_path(rel_path)
    resolved_ref = validate_git_revision(repo_path, ref)

    if resolved_ref == "WORKTREE":
        target = (repo_path / safe_rel).resolve()
        if not str(target).startswith(str(repo_path.resolve())):
            raise RepoInspectionError(f"File path '{safe_rel}' escapes repository root '{repo_path}'.")
        if not target.exists() or not target.is_file():
            raise RepoInspectionError(
                f"File '{safe_rel}' not found in working tree of '{repo_path.name}'."
            )
        return target.read_text(encoding="utf-8")

    res = _run_git_cmd(repo_path, ["show", f"{resolved_ref}:{safe_rel}"])
    if res.returncode != 0:
        raise RepoInspectionError(
            f"File '{safe_rel}' not found at revision '{ref}' in '{repo_path.name}': "
            f"{(res.stderr or '').strip()}"
        )
    return res.stdout


def get_repo_diff(
    repo_path: Path,
    base_ref: str,
    target_ref: str,
    rel_path: str | None = None,
) -> str:
    """Produce a unified git diff between base_ref and target_ref."""
    resolved_base = validate_git_revision(repo_path, base_ref)
    if resolved_base == "WORKTREE":
        raise RepoInspectionError("Base revision cannot be 'WORKTREE'; specify a commit, branch, or tag.")
    resolved_target = validate_git_revision(repo_path, target_ref)

    args = ["diff", resolved_base]
    if resolved_target != "WORKTREE":
        args.append(resolved_target)
    if rel_path and rel_path.strip():
        args.extend(["--", _sanitize_rel_path(rel_path)])

    res = _run_git_cmd(repo_path, args)
    if res.returncode != 0:
        return f"# Unable to generate diff: {(res.stderr or '').strip()}"
    return res.stdout.strip() or f"# No diff changes between {base_ref} and {target_ref}"


def list_repo_files_at_revision(repo_path: Path, ref: str) -> list[str]:
    """List all tracked relative file paths at the given revision (or working tree)."""
    resolved_ref = validate_git_revision(repo_path, ref)
    if resolved_ref == "WORKTREE":
        files: list[str] = []
        for p in repo_path.rglob("*"):
            if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts and ".venv" not in p.parts:
                files.append(p.relative_to(repo_path).as_posix())
        return sorted(files)

    res = _run_git_cmd(repo_path, ["ls-tree", "-r", "--name-only", resolved_ref])
    if res.returncode != 0:
        raise RepoInspectionError(f"Failed to list files at revision '{ref}' in '{repo_path.name}'.")
    return sorted(line.strip() for line in res.stdout.splitlines() if line.strip())


def discover_provider_contract_file(repo_path: Path, ref: str) -> str:
    """Auto-discover a suitable .json or .py contract file in a provider repository."""
    candidates = list_repo_files_at_revision(repo_path, ref)
    ignored_json = {"package.json", "package-lock.json", "tsconfig.json", "scenario.json", "expected_finding.json"}

    # 1. Check .json files first
    for rel in candidates:
        name = PurePosixPath(rel).name.lower()
        if name.endswith(".json") and name not in ignored_json and not name.startswith("."):
            try:
                raw = read_repo_file_at_revision(repo_path, ref, rel)
                parse_contract_content(raw, source_label=rel)
                return rel
            except ContractAnalysisError:
                continue

    # 2. Check non-test .py files for extractable dict return or model class
    for rel in candidates:
        name = PurePosixPath(rel).name.lower()
        if name.endswith(".py") and not name.startswith("test_") and not name.endswith("_test.py") and name != "conftest.py":
            try:
                raw = read_repo_file_at_revision(repo_path, ref, rel)
                parse_contract_content(raw, source_label=rel)
                return rel
            except ContractAnalysisError:
                continue

    raise ContractAnalysisError(
        f"Could not auto-discover an extractable REST JSON (.json) or Python (.py) contract "
        f"in repository '{repo_path.name}' at revision '{ref}'."
    )


def discover_consumer_python_files(repo_path: Path, ref: str) -> list[str]:
    """Discover non-test Python source files in a consumer repository at the specified revision."""
    candidates = list_repo_files_at_revision(repo_path, ref)
    py_files: list[str] = []
    for rel in candidates:
        parts_lower = [p.lower() for p in PurePosixPath(rel).parts]
        name = parts_lower[-1]
        if (
            name.endswith(".py")
            and "tests" not in parts_lower
            and "test" not in parts_lower
            and not name.startswith("test_")
            and not name.endswith("_test.py")
            and name not in {"conftest.py", "setup.py"}
        ):
            py_files.append(rel)
    return py_files
