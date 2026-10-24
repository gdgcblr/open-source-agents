"""Small read-only repository tools exposed to the model."""

from __future__ import annotations

from pathlib import Path

MAX_FILE_BYTES = 128_000
MAX_MATCHES = 80
IGNORED = {
    ".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".terraform", ".venv",
    "build", "dist", "node_modules", "venv", "__pycache__",
}
SECRET_NAMES = {
    ".git-credentials", ".netrc", ".npmrc", ".pypirc", "accesstokens.json",
    "application_default_credentials.json", "credentials", "credentials.json", "id_dsa",
    "id_ecdsa", "id_ed25519", "id_rsa", "kubeconfig",
    "secrets", "secrets.json", "secrets.yaml", "secrets.yml", "service-account.json",
}


def _is_sensitive(path: Path) -> bool:
    name = path.name.casefold()
    parts = {part.casefold() for part in path.parts}
    return (
        any(part == ".env" or part.startswith(".env.") for part in parts)
        or name in SECRET_NAMES
        or name.endswith((".pem", ".key", ".p12", ".pfx", ".tfstate"))
        or "service-account" in name
        or (name.startswith("id_") and not name.endswith(".pub"))
        or ".ssh" in parts
        or ".aws" in parts
        or ".azure" in parts
        or (".docker" in parts and name == "config.json")
        or (".kube" in parts and name == "config")
    )


def checked_repo(repo: Path) -> Path:
    resolved = repo.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("Repository must be a directory.")
    return resolved


def list_files(repo: Path, limit: int = 200) -> list[str]:
    root = checked_repo(repo)
    found = []
    for path in sorted(root.rglob("*")):
        if any(part.casefold() in IGNORED for part in path.relative_to(root).parts):
            continue
        if path.is_symlink() or _is_sensitive(path):
            continue
        if path.is_file():
            found.append(path.relative_to(root).as_posix())
            if len(found) >= min(max(limit, 1), 500):
                break
    return found


def read_file(repo: Path, relative_path: str) -> str:
    root = checked_repo(repo)
    candidate = root / relative_path
    if _is_sensitive(candidate):
        raise ValueError("Credential-like files are excluded from agent inspection.")
    try:
        relative_candidate = candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Requested path is outside the repository.") from exc
    cursor = root
    for part in relative_candidate.parts:
        if part in {"", "."}:
            continue
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("Symlinked paths are excluded from agent inspection.")
    target = candidate.resolve(strict=True)
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError("Requested path is outside the repository or is not a file.")
    if any(part.casefold() in IGNORED for part in target.relative_to(root).parts):
        raise ValueError("Generated, dependency, and VCS metadata files are excluded from inspection.")
    if _is_sensitive(target):
        raise ValueError("Credential-like files are excluded from agent inspection.")
    if target.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"File exceeds the {MAX_FILE_BYTES}-byte read limit.")
    return target.read_text(encoding="utf-8", errors="replace")


def search_text(repo: Path, query: str) -> list[dict[str, int | str]]:
    if not query or len(query) > 200:
        raise ValueError("Search query must contain 1 to 200 characters.")
    root = checked_repo(repo)
    matches = []
    for name in list_files(root, 500):
        path = root / name
        try:
            if path.is_symlink() or _is_sensitive(path):
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if query.casefold() in line.casefold():
                    matches.append({"path": name, "line": line_no, "text": line[:500]})
                    if len(matches) >= MAX_MATCHES:
                        return matches
        except OSError:
            continue
    return matches
