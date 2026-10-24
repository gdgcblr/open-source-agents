"""Tools the README drafter uses to inspect a project folder.

Every tool is confined to PROJECT_DIR. Nothing outside it is read, secret
files such as .env are never opened, and token-like strings are redacted
before any text reaches the model.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import tomllib
from collections import Counter
from pathlib import Path

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".adk", "dist", "build",
    ".next", ".nuxt", "target", ".idea", ".vscode", "coverage", "htmlcov", ".gradle",
}
SENSITIVE_PATTERNS = [
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.keystore",
    "id_rsa*", "id_ed25519*", "credentials.json", "service-account*.json",
    ".npmrc", ".pypirc", ".netrc",
]
ENV_TEMPLATES = (".env.example", ".env.sample", ".env.template")
SECRET_VALUE_RE = re.compile(
    r"sk-[A-Za-z0-9_-]{16,}"            # OpenAI / Anthropic style keys
    r"|AIza[0-9A-Za-z_-]{30,}"          # Google API keys
    r"|gh[pousr]_[A-Za-z0-9]{30,}"      # GitHub tokens
    r"|AKIA[0-9A-Z]{16}"                # AWS access key IDs
    r"|xox[abprs]-[A-Za-z0-9-]{10,}"    # Slack tokens
)
LANGUAGES = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".go": "Go", ".rs": "Rust",
    ".java": "Java", ".kt": "Kotlin", ".rb": "Ruby", ".php": "PHP", ".cs": "C#",
    ".cpp": "C++", ".c": "C", ".swift": "Swift", ".dart": "Dart", ".sh": "Shell",
}
LICENSE_MARKERS = [  # (phrase in the license text, SPDX id); first match wins
    ("Permission is hereby granted, free of charge", "MIT"),
    ("Apache License", "Apache-2.0"),
    ("GNU AFFERO GENERAL PUBLIC LICENSE", "AGPL-3.0"),
    ("GNU LESSER GENERAL PUBLIC LICENSE", "LGPL"),
    ("GNU GENERAL PUBLIC LICENSE", "GPL"),
    ("Mozilla Public License", "MPL-2.0"),
    ("Permission to use, copy, modify, and/or distribute", "ISC"),
    ("Redistribution and use in source and binary forms", "BSD"),
    ("This is free and unencumbered software", "Unlicense"),
]
ENTRY_POINT_NAMES = {
    "main.py", "app.py", "cli.py", "server.py", "manage.py", "agent.py", "__main__.py",
    "index.js", "index.ts", "main.js", "main.ts", "server.js", "server.ts",
    "main.go", "main.rs",
}

# Gemma chat-template tokens that occasionally leak into replies.
LEAKED_TOKEN_RE = re.compile(r"<\|?(?:channel|turn)\|?>")

MAX_FILE_CHARS = 8000
MAX_LISTED_FILES = 300
KEY_FILES_BUDGET_CHARS = 30000
KEY_CONFIG_FILES = ("Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml", "Makefile")
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


def _project_root() -> Path:
    return Path(os.getenv("PROJECT_DIR") or os.getcwd()).resolve()


def _project_name(root: Path) -> str:
    return os.getenv("PROJECT_NAME") or root.name


def _is_sensitive(name: str) -> bool:
    if name in ENV_TEMPLATES:
        return False
    return any(fnmatch.fnmatch(name, pattern) for pattern in SENSITIVE_PATTERNS)


def _redact(text: str) -> str:
    return SECRET_VALUE_RE.sub("[REDACTED]", text)


def _walk_files(root: Path, max_depth: int):
    """Yields (relative path, is_sensitive) for files under root, pruning SKIP_DIRS."""
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        dirnames[:] = sorted(
            d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info")
        )
        if len(rel_dir.parts) + 1 >= max_depth:
            dirnames[:] = []
        for name in sorted(filenames):
            if name != ".DS_Store":
                yield rel_dir / name, _is_sensitive(name)


def _read_text(path: Path, limit: int) -> str:
    """Reads at most `limit` characters without loading a huge file into memory."""
    with path.open("rb") as f:
        return f.read(limit * 4).decode("utf-8", errors="replace")[:limit]


def list_project_files(max_depth: int = 4) -> dict:
    """Lists the files in the project folder, skipping dependency, build and secret files.

    Args:
        max_depth: How many folder levels deep to list. Defaults to 4.

    Returns:
        A dict with the project name and the relative path of every file found.
    """
    root = _project_root()
    if not root.is_dir():
        return {"status": "error", "error_message": f"Project folder not found: {root}"}

    files, skipped = [], 0
    for rel_path, sensitive in _walk_files(root, max(1, int(max_depth))):
        if sensitive:
            skipped += 1
        else:
            files.append(rel_path.as_posix())

    return {
        "status": "success",
        "project_name": _project_name(root),
        "file_count": len(files),
        "files": files[:MAX_LISTED_FILES],
        "truncated": len(files) > MAX_LISTED_FILES,
        "secret_files_hidden": skipped,
    }


def _parse_requirements(path: Path) -> dict:
    lines = [line.strip() for line in _read_text(path, MAX_FILE_CHARS).splitlines()]
    return {"dependencies": [l for l in lines if l and not l.startswith(("#", "-"))][:40]}


def _parse_pyproject(path: Path) -> dict:
    data = tomllib.loads(_read_text(path, MAX_FILE_CHARS * 2))
    project = data.get("project", {})
    poetry = data.get("tool", {}).get("poetry", {})
    return {
        "name": project.get("name") or poetry.get("name"),
        "description": project.get("description") or poetry.get("description"),
        "requires_python": project.get("requires-python"),
        "dependencies": project.get("dependencies") or list(poetry.get("dependencies", {})),
        "scripts": list(project.get("scripts", {}) or poetry.get("scripts", {})),
    }


def _parse_package_json(path: Path) -> dict:
    data = json.loads(_read_text(path, MAX_FILE_CHARS * 2))
    return {
        "name": data.get("name"),
        "description": data.get("description"),
        "scripts": data.get("scripts", {}),
        "dependencies": list(data.get("dependencies", {})),
        "dev_dependencies": list(data.get("devDependencies", {})),
        "engines": data.get("engines", {}),
        "bin": data.get("bin"),
    }


def _parse_cargo(path: Path) -> dict:
    data = tomllib.loads(_read_text(path, MAX_FILE_CHARS))
    package = data.get("package", {})
    return {
        "name": package.get("name"),
        "description": package.get("description"),
        "dependencies": list(data.get("dependencies", {})),
    }


def _parse_go_mod(path: Path) -> dict:
    lines = _read_text(path, MAX_FILE_CHARS).splitlines()
    return {"module_and_go_version": [l for l in lines if l.startswith(("module ", "go "))]}


def _parse_dockerfile(path: Path) -> dict:
    keywords = ("FROM", "EXPOSE", "CMD", "ENTRYPOINT")
    lines = _read_text(path, MAX_FILE_CHARS).splitlines()
    return {"instructions": [l.strip() for l in lines if l.strip().upper().startswith(keywords)]}


def _parse_compose(path: Path) -> dict:
    text = _read_text(path, MAX_FILE_CHARS)
    return {"services": re.findall(r"^  ([A-Za-z0-9_.-]+):\s*$", text, flags=re.MULTILINE)}


def _parse_env_template(path: Path) -> dict:
    """Returns variable names only. Values are dropped even from example files."""
    names = re.findall(r"^\s*(#\s*)?([A-Z][A-Z0-9_]*)\s*=", _read_text(path, MAX_FILE_CHARS), re.M)
    return {
        "variables": [name for commented, name in names if not commented],
        "commented_out_variables": [name for commented, name in names if commented],
    }


def _parse_makefile(path: Path) -> dict:
    targets = re.findall(r"^([A-Za-z0-9_-]+):(?!=)", _read_text(path, MAX_FILE_CHARS), re.M)
    return {"targets": targets[:20]}


MANIFEST_PARSERS = {
    "requirements.txt": _parse_requirements,
    "pyproject.toml": _parse_pyproject,
    "package.json": _parse_package_json,
    "Cargo.toml": _parse_cargo,
    "go.mod": _parse_go_mod,
    "Dockerfile": _parse_dockerfile,
    "docker-compose.yml": _parse_compose,
    "docker-compose.yaml": _parse_compose,
    "compose.yml": _parse_compose,
    "compose.yaml": _parse_compose,
    "Makefile": _parse_makefile,
    **{name: _parse_env_template for name in ENV_TEMPLATES},
}


def detect_project_stack() -> dict:
    """Detects the project's languages, dependencies, run commands and settings.

    Reads the manifest files in the project root, such as requirements.txt,
    pyproject.toml, package.json, Dockerfile, docker-compose.yml and .env.example.
    Only variable names are taken from .env.example, never their values.

    Returns:
        A dict with detected languages, likely entry points and the parsed manifests.
    """
    root = _project_root()
    if not root.is_dir():
        return {"status": "error", "error_message": f"Project folder not found: {root}"}

    manifests = {}
    for name, parser in MANIFEST_PARSERS.items():
        path = root / name
        if path.is_file():
            try:
                manifests[name] = parser(path)
            except (ValueError, OSError, AttributeError) as exc:
                manifests[name] = {"error": f"Could not parse: {exc}"}

    languages, entry_points = Counter(), []
    for rel_path, sensitive in _walk_files(root, max_depth=4):
        if sensitive:
            continue
        if rel_path.suffix in LANGUAGES:
            languages[LANGUAGES[rel_path.suffix]] += 1
        if rel_path.name in ENTRY_POINT_NAMES and len(rel_path.parts) <= 3:
            entry_points.append(rel_path.as_posix())

    readme = next((p.name for p in root.glob("README*") if p.is_file()), None)
    license_file = next((p for p in root.glob("LICEN[CS]E*") if p.is_file()), None)
    license_text = " ".join(_read_text(license_file, 3000).split()) if license_file else ""
    license_name = next((spdx for phrase, spdx in LICENSE_MARKERS if phrase.lower() in license_text.lower()), None)

    return {
        "status": "success",
        "project_name": _project_name(root),
        "languages_by_file_count": dict(languages.most_common()),
        "likely_entry_points": entry_points[:15],
        "existing_readme": readme,
        "license": {
            "file": license_file.name if license_file else None,
            "detected": license_name,
            "excerpt": license_text[:120] or None,
        },
        "manifests": json.loads(_redact(json.dumps(manifests))),
    }


def read_file(path: str) -> dict:
    """Reads one text file from the project folder.

    Args:
        path: The file path relative to the project folder, as returned by list_project_files.

    Returns:
        A dict with the file content (cut short if the file is very long) or an error message.
    """
    root = _project_root()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        return {"status": "error", "error_message": "Only files inside the project folder can be read."}
    if _is_sensitive(target.name):
        return {
            "status": "error",
            "error_message": "This file may contain secrets, so it is not read. "
            "Document it as a file the user creates, for example from .env.example.",
        }
    if not target.is_file():
        return {"status": "error", "error_message": f"File not found: {path}"}

    with target.open("rb") as f:
        head = f.read(1024)
    if b"\x00" in head:
        return {"status": "error", "error_message": f"{path} is a binary file."}

    text = _read_text(target, MAX_FILE_CHARS + 1)
    return {
        "status": "success",
        "path": path,
        "content": _redact(text[:MAX_FILE_CHARS]),
        "truncated": len(text) > MAX_FILE_CHARS,
    }


def read_key_files() -> dict:
    """Reads the files that best explain the project, picked automatically.

    Picks an existing README, likely entry points, Docker and Makefile config,
    then the remaining source files closest to the project root, until a size
    budget is used up.

    Returns:
        A dict mapping each chosen file path to its content.
    """
    root = _project_root()
    if not root.is_dir():
        return {"status": "error", "error_message": f"Project folder not found: {root}"}

    files = [p for p, sensitive in _walk_files(root, max_depth=4) if not sensitive]
    readmes = [p for p in files if len(p.parts) == 1 and p.name.upper().startswith("README")]
    entry_points = [p for p in files if p.name in ENTRY_POINT_NAMES and len(p.parts) <= 3]
    configs = [p for p in files if len(p.parts) == 1 and p.name in KEY_CONFIG_FILES]
    sources = sorted(
        (p for p in files if p.suffix in LANGUAGES and not p.name.startswith("test")),
        key=lambda p: (len(p.parts), p.as_posix()),
    )

    chosen, contents, budget = [], {}, KEY_FILES_BUDGET_CHARS
    for path in readmes + entry_points + configs + sources:
        if path in chosen or budget <= 0:
            continue
        result = read_file(path.as_posix())
        if result["status"] != "success":
            continue
        chosen.append(path)
        contents[path.as_posix()] = result["content"][:budget]
        budget -= len(contents[path.as_posix()])

    skipped = [p.as_posix() for p in files if p not in chosen and p.suffix in LANGUAGES]
    return {
        "status": "success",
        "files": contents,
        "other_source_files_not_read": skipped[:50],
    }


def inspect_project() -> dict:
    """Inspects the project in one step: its stack, manifests and most important files.

    Returns:
        A dict with "stack" (languages, entry points, parsed manifests) and
        "key_files" (the content of the files that best explain the project).
    """
    stack = detect_project_stack()
    if stack["status"] != "success":
        return stack
    return {"status": "success", "stack": stack, "key_files": read_key_files()}


def extract_readme(text: str) -> str | None:
    """Returns the README part of a model reply, or None if the reply holds no README.

    The README starts at the '# Title' heading before the first '## ' section,
    even when the model glues an intro sentence onto the title line.
    """
    text = LEAKED_TOKEN_RE.sub("", text)
    first_section = re.search(r"^##\s", text, flags=re.MULTILINE)
    if not first_section:
        return None
    title = text.rfind("# ", 0, first_section.start())
    while title > 0 and text[title - 1] == "#":
        title = text.rfind("# ", 0, title - 1)
    if title == -1:
        return None
    return text[title:].strip() + "\n"


def save_readme_draft(markdown: str) -> dict:
    """Saves a README draft as README.draft.md in the output folder.

    Called by the agent's after-model callback, not by the model: small local
    models write long documents more reliably as a reply than as a tool argument.
    """
    output_dir = Path(os.getenv("OUTPUT_DIR") or DEFAULT_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "README.draft.md"
    target.write_text(_redact(markdown), encoding="utf-8")
    return {"status": "success", "saved_to": str(target), "characters": len(markdown)}
