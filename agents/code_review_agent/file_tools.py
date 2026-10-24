from pathlib import Path

MAX_FILE_BYTES = 100_000

ALLOWED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs",
    ".cs", ".cpp", ".c", ".h", ".hpp", ".php", ".rb", ".swift",
    ".kt", ".kts", ".sql", ".html", ".css", ".sh", ".ps1",
}

BLOCKED_NAMES = {
    ".env", ".env.local", ".env.production", "credentials.json",
    "secrets.json", "id_rsa", "id_ed25519",
}


def read_source_file(path: str) -> dict:
    """Read a supported source-code file under the current working directory.

    Args:
        path: Relative path to a source-code file from the current working directory.

    Returns:
        A dictionary containing the file name and source text, or a clear error.
    """
    root = Path.cwd().resolve()
    requested = Path(path)

    if requested.is_absolute():
        return {"status": "error", "message": "Use a relative file path."}

    try:
        target = (root / requested).resolve()
        target.relative_to(root)
    except (OSError, ValueError):
        return {
            "status": "error",
            "message": "The path must stay inside the current working directory.",
        }

    if any(part.startswith(".") for part in requested.parts):
        return {"status": "error", "message": "Hidden paths are not allowed."}

    if target.name.lower() in BLOCKED_NAMES:
        return {"status": "error", "message": "This file type is not allowed."}

    if not target.is_file():
        return {"status": "error", "message": "The requested file does not exist."}

    if target.suffix.lower() not in ALLOWED_EXTENSIONS:
        return {
            "status": "error",
            "message": "Unsupported file extension. Provide a source-code file.",
        }

    try:
        size = target.stat().st_size
        if size > MAX_FILE_BYTES:
            return {
                "status": "error",
                "message": f"File is larger than the {MAX_FILE_BYTES}-byte limit.",
            }

        content = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {
            "status": "error",
            "message": "The file could not be read as UTF-8 text.",
        }

    return {
        "status": "success",
        "file_name": target.relative_to(root).as_posix(),
        "language": target.suffix.lstrip("."),
        "content": content,
        "line_count": len(content.splitlines()),
    }
