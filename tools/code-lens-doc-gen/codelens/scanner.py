"""
Codebase Scanner — Walks the file tree and builds a structured map.

This module is responsible for:
- Recursively walking a directory tree
- Filtering out ignored directories and files
- Detecting file languages from extensions
- Reading file contents (respecting size limits)
- Building a complete CodebaseMap representation

No LLM calls happen here — this is pure local analysis.
"""

import os
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .config import Config

console = Console()


def scan_codebase(root_path: str, config: Config) -> dict:
    """
    Scan an entire codebase and return a structured map.

    Args:
        root_path: Absolute or relative path to the codebase root.
        config: Configuration object.

    Returns:
        A dict representing the full codebase structure:
        {
            "root_path": str,
            "total_files": int,
            "total_lines": int,
            "languages": {language: file_count},
            "files": [
                {
                    "path": str (relative),
                    "language": str,
                    "category": str ("source"|"config"|"doc"|"other"),
                    "size_bytes": int,
                    "line_count": int,
                    "content": str,
                }
            ],
            "file_tree": dict (nested directory structure),
        }
    """
    root = Path(root_path).resolve()

    if not root.is_dir():
        console.print(f"[red]Error:[/red] '{root_path}' is not a valid directory.")
        return {}

    all_extensions = {}
    all_extensions.update(config.source_extensions)
    all_extensions.update(config.config_extensions)
    all_extensions.update(config.doc_extensions)

    files = []
    languages = {}
    total_lines = 0
    file_tree = {}
    skipped_count = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning codebase...", total=None)

        for dirpath, dirnames, filenames in os.walk(root):
            # Filter out ignored directories (modifying dirnames in-place
            # prevents os.walk from descending into them)
            dirnames[:] = [
                d for d in dirnames
                if d not in config.ignore_dirs
            ]

            rel_dir = os.path.relpath(dirpath, root)

            for filename in filenames:
                if filename in config.ignore_files:
                    continue

                filepath = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(filepath, root)

                # Normalize path separators to forward slashes
                rel_path = rel_path.replace("\\", "/")

                # Get file size
                try:
                    file_size = os.path.getsize(filepath)
                except OSError:
                    skipped_count += 1
                    continue

                # Skip files exceeding the size limit
                if file_size > config.max_file_size:
                    skipped_count += 1
                    continue

                # Detect language/type from extension
                ext = Path(filename).suffix.lower()
                language = "unknown"
                category = "other"

                # Check for special filenames first
                lower_name = filename.lower()
                if lower_name == "dockerfile":
                    language = "dockerfile"
                    category = "config"
                elif lower_name == "makefile":
                    language = "makefile"
                    category = "config"
                elif lower_name in ("readme.md", "contributing.md", "changelog.md", "license"):
                    language = config.doc_extensions.get(ext, "text")
                    category = "doc"
                elif ext in config.source_extensions:
                    language = config.source_extensions[ext]
                    category = "source"
                elif ext in config.config_extensions:
                    language = config.config_extensions[ext]
                    category = "config"
                elif ext in config.doc_extensions:
                    language = config.doc_extensions[ext]
                    category = "doc"

                # Skip truly unknown binary files
                if language == "unknown" and ext not in (".txt", ""):
                    # Try to check if it's a text file
                    if not _is_text_file(filepath):
                        skipped_count += 1
                        continue

                # Read file content
                content = _read_file_safe(filepath)
                if content is None:
                    skipped_count += 1
                    continue

                line_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
                total_lines += line_count

                # Track language counts
                languages[language] = languages.get(language, 0) + 1

                # Build the file tree structure
                _add_to_tree(file_tree, rel_path)

                files.append({
                    "path": rel_path,
                    "language": language,
                    "category": category,
                    "size_bytes": file_size,
                    "line_count": line_count,
                    "content": content,
                })

                progress.update(task, description=f"Scanning: {rel_path}")

    codebase_map = {
        "root_path": str(root),
        "total_files": len(files),
        "total_lines": total_lines,
        "skipped_files": skipped_count,
        "languages": languages,
        "files": files,
        "file_tree": file_tree,
    }

    return codebase_map


def _read_file_safe(filepath: str) -> str | None:
    """
    Read a file's content with graceful encoding fallback.
    Returns None if the file cannot be read as text.
    """
    encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]

    for encoding in encodings:
        try:
            with open(filepath, "r", encoding=encoding) as f:
                return f.read()
        except (UnicodeDecodeError, ValueError):
            continue
        except (OSError, PermissionError):
            return None

    return None


def _is_text_file(filepath: str, sample_size: int = 8192) -> bool:
    """
    Heuristic check: read a chunk of the file and look for null bytes.
    Binary files almost always contain null bytes; text files don't.
    """
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(sample_size)
        return b"\x00" not in chunk
    except (OSError, PermissionError):
        return False


def _add_to_tree(tree: dict, rel_path: str) -> None:
    """Add a relative file path into a nested dict tree structure."""
    parts = rel_path.split("/")
    current = tree
    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        current = current[part]
    # Leaf nodes are files, represented as None
    current[parts[-1]] = None


def format_file_tree(tree: dict, prefix: str = "") -> str:
    """
    Format a file tree dict into a visual tree string.
    Used for CLI display and documentation output.
    """
    lines = []
    items = sorted(tree.items(), key=lambda x: (x[1] is not None, x[0]))

    for i, (name, subtree) in enumerate(items):
        is_last = (i == len(items) - 1)
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{name}")

        if subtree is not None:  # It's a directory
            extension = "    " if is_last else "│   "
            lines.append(format_file_tree(subtree, prefix + extension))

    return "\n".join(lines)
