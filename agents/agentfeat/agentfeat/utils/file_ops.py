"""File operations, diffing, safety boundaries, and backup management for AgentFeat."""

import difflib
import fnmatch
import os
import shutil
import time
from pathlib import Path
from typing import List, Optional, Set, Tuple

from agentfeat.models.schemas import FileChange

# Sensitive files and directories that should never be overwritten or modified by the agent
PROTECTED_PATTERNS: Set[str] = {
    ".env*",
    "*.env",
    ".git*",
    "*.pem",
    "*.key",
    "*.secret",
    "id_rsa*",
    "id_ed25519*",
    ".aws*",
    ".ssh*",
    ".bashrc",
    ".zshrc",
}


def is_path_safe(target_root: Path, file_path_str: str) -> Tuple[bool, str]:
    """Verify that a relative file path is strictly within target_root and not protected.

    Returns:
        (is_safe, error_message)
    """
    if not file_path_str or not file_path_str.strip():
        return False, "File path cannot be empty"

    # Normalize path string
    clean_path_str = file_path_str.strip()

    # Block explicit absolute paths trying to target system root
    if clean_path_str.startswith("/") or (len(clean_path_str) > 1 and clean_path_str[1] == ":"):
        return False, f"Absolute paths are forbidden: '{file_path_str}'"

    # Check for directory traversal sequences
    parts = Path(clean_path_str).parts
    if ".." in parts:
        return False, f"Directory traversal (..) is forbidden: '{file_path_str}'"

    # Check protected patterns against filename and relative path parts
    filename = Path(clean_path_str).name
    for pattern in PROTECTED_PATTERNS:
        if fnmatch.fnmatch(filename, pattern):
            return False, f"Target file '{filename}' matches protected sensitive pattern '{pattern}'"
        for part in parts:
            if fnmatch.fnmatch(part, pattern):
                return False, f"Target path component '{part}' matches protected sensitive pattern '{pattern}'"

    # Verify canonical resolution is within root
    try:
        resolved_root = target_root.resolve()
        resolved_target = (resolved_root / clean_path_str).resolve()

        # In Python 3.9+, use os.path.commonpath for reliable containment check
        common = os.path.commonpath([str(resolved_root), str(resolved_target)])
        if common != str(resolved_root):
            return False, f"Path '{file_path_str}' escapes target root directory '{target_root}'"
    except Exception as e:
        return False, f"Invalid path resolution: {e}"

    return True, ""


def resolve_safe_path(target_root: Path, file_path_str: str) -> Path:
    """Resolve a relative path against target_root, raising PermissionError if unsafe."""
    is_safe, err = is_path_safe(target_root, file_path_str)
    if not is_safe:
        raise PermissionError(f"Security violation: {err}")
    return (target_root.resolve() / file_path_str).resolve()


def read_file_safe(file_path: Path, max_bytes: int = 150_000) -> Tuple[str, bool]:
    """Read a text file safely up to max_bytes.

    Returns:
        (content, is_truncated)
    """
    if not file_path.is_file():
        return "", False

    try:
        size = file_path.stat().st_size
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            if size > max_bytes:
                content = f.read(max_bytes)
                return content, True
            return f.read(), False
    except Exception:
        return "", False


def write_file_safe(file_path: Path, content: str) -> None:
    """Write content to file, creating parent directories if needed."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)


def generate_diff(original: Optional[str], modified: str, file_name: str) -> str:
    """Generate a clean unified diff formatted string."""
    orig_lines = (original or "").splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)

    diff = difflib.unified_diff(
        orig_lines,
        mod_lines,
        fromfile=f"a/{file_name}",
        tofile=f"b/{file_name}",
        n=3,
    )
    return "".join(diff)


def create_backup(target_root: Path, file_paths: List[str]) -> Path:
    """Create a timestamped backup directory of files before modifying them."""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_dir = target_root / ".agentfeat_backup" / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    for rel_path in file_paths:
        try:
            safe_target = resolve_safe_path(target_root, rel_path)
            if safe_target.is_file():
                rel_from_root = safe_target.relative_to(target_root.resolve())
                dst = backup_dir / rel_from_root
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(safe_target, dst)
        except PermissionError:
            continue

    return backup_dir


def restore_backup(backup_dir: Path, target_root: Path) -> List[str]:
    """Restore previously backed up files to target_root.

    Returns:
        List of restored relative file paths.
    """
    if not backup_dir.is_dir():
        raise FileNotFoundError(f"Backup directory not found: {backup_dir}")

    restored_files: List[str] = []
    resolved_root = target_root.resolve()

    for root, _, files in os.walk(backup_dir):
        for file in files:
            backup_file_path = Path(root) / file
            rel_path = backup_file_path.relative_to(backup_dir)

            # Verify safe target
            safe_dst = resolve_safe_path(resolved_root, str(rel_path))
            safe_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file_path, safe_dst)
            restored_files.append(str(rel_path))

    return restored_files


def apply_file_changes(target_root: Path, changes: List[FileChange], create_backups: bool = True) -> Optional[Path]:
    """Safely apply a list of FileChange objects to disk within target_root."""
    paths_to_touch = [c.file_path for c in changes]
    backup_dir = None
    if create_backups:
        backup_dir = create_backup(target_root, paths_to_touch)

    for change in changes:
        target = resolve_safe_path(target_root, change.file_path)

        if change.action in ("create", "modify"):
            write_file_safe(target, change.new_content)
        elif change.action == "delete":
            if target.is_file():
                target.unlink()

    return backup_dir


def get_file_tree(root_dir: Path, max_depth: int = 3, max_files: int = 60) -> str:
    """Generate a clean ASCII file tree representation, skipping hidden/ignored directories."""
    ignore_dirs = {
        ".git", ".venv", "venv", "__pycache__", "node_modules",
        ".agentfeat_backup", ".pytest_cache", ".idea", ".vscode", "dist", "build"
    }

    lines = [f"{root_dir.name}/"]
    count = 0

    def _walk(directory: Path, prefix: str, depth: int):
        nonlocal count
        if depth > max_depth or count >= max_files:
            return

        try:
            entries = sorted(list(directory.iterdir()), key=lambda e: (not e.is_dir(), e.name.lower()))
        except Exception:
            return

        visible_entries = [e for e in entries if e.name not in ignore_dirs and not e.name.startswith(".")]

        for i, entry in enumerate(visible_entries):
            if count >= max_files:
                lines.append(f"{prefix}... (truncated)")
                return

            count += 1
            is_last = (i == len(visible_entries) - 1)
            connector = "└── " if is_last else "├── "
            child_prefix = "    " if is_last else "│   "

            if entry.is_dir():
                lines.append(f"{prefix}{connector}{entry.name}/")
                _walk(entry, prefix + child_prefix, depth + 1)
            else:
                lines.append(f"{prefix}{connector}{entry.name}")

    _walk(root_dir, "", 1)
    return "\n".join(lines)
