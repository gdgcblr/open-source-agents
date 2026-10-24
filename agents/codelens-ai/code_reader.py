
from pathlib import Path

SUPPORTED_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java"}


def read_source_file(file_path: str) -> str:
    """Read a supported source-code file and return its contents."""
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if not path.is_file():
        raise ValueError(f"Not a file: {path}")

    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {path.suffix}")

    source = path.read_text(encoding="utf-8")

    if not source.strip():
        raise ValueError("The source file is empty.")

    return source


def split_code(source: str, max_lines: int = 100) -> list[str]:
    """Split source code into manageable line-based chunks."""
    if max_lines < 1:
        raise ValueError("max_lines must be greater than zero.")

    lines = source.splitlines()

    return [
        "\n".join(lines[i:i + max_lines])
        for i in range(0, len(lines), max_lines)
    ]

from pathlib import Path

IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".next",
    "dist",
    "build",
    "output",
}

def discover_source_files(directory: str) -> list[Path]:
    """Find supported source files while skipping generated and dependency folders."""
    root = Path(directory).expanduser().resolve()

    if not root.exists():
        raise FileNotFoundError(f"Directory not found: {root}")

    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")

    source_files = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        # Skip files inside dependency, generated, or hidden directories.
        relative_path = path.relative_to(root)

        if any(
            part.startswith(".") or part in IGNORED_DIRECTORIES
            for part in relative_path.parts[:-1]
        ):
            continue

        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        source_files.append(path)

    return sorted(source_files)
