"""Read-only repository scanning and evidence collection."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

MAX_FILE_SIZE = 1_000_000
MAX_FILES = 10_000
MAX_STARTER_TASKS = 5
MAX_SECTION_FINDINGS = 20
MAX_CONTRIBUTION_FINDINGS = 8

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".next",
    "coverage",
    "template",
    "templates",
    "fixture",
    "fixtures",
    "testdata",
}
TASK_EXCLUDED_DIRS = {"test", "tests", "example", "examples"}
SENSITIVE_NAMES = {
    ".env",
    "credentials.json",
    "secrets.json",
    "service-account.json",
}
SOURCE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".mts",
    ".cts",
    ".ps1",
    ".psm1",
    ".bat",
    ".cmd",
    ".dart",
    ".ex",
    ".exs",
    ".erl",
    ".hrl",
    ".fs",
    ".fsx",
    ".groovy",
    ".gradle",
    ".hs",
    ".lhs",
    ".lua",
    ".m",
    ".mm",
    ".pl",
    ".pm",
    ".r",
    ".clj",
    ".cljs",
    ".cljc",
    ".lisp",
    ".el",
    ".ml",
    ".mli",
    ".pas",
    ".pp",
    ".vb",
    ".v",
    ".sv",
    ".sol",
    ".sql",
    ".tf",
    ".hcl",
    ".proto",
    ".vue",
    ".svelte",
    ".scala",
    ".sc",
    ".jl",
    ".elm",
    ".purs",
    ".nix",
    ".bzl",
    ".f",
    ".for",
    ".f90",
    ".f95",
    ".cbl",
    ".cob",
}
MANIFEST_NAMES = {
    "Cargo.toml",
    "Gemfile",
    "Makefile",
    "Pipfile",
    "go.mod",
    "justfile",
    "package.json",
    "pom.xml",
    "pyproject.toml",
    "requirements.txt",
    "setup.cfg",
    "setup.py",
    "tox.ini",
}
SECRET_NAME_PARTS = ("secret", "credential", "private-key", "id_rsa")
TODO_PATTERN = re.compile(
    r"^\s*(?:#|//|--|/\*+|\*|<!--|;|%)\s*(TODO|FIXME|XXX)\b\s*[:\-]?\s*(.*?)\s*(?:\*/|-->)?\s*$",
    re.IGNORECASE,
)
TEST_COMMAND_PATTERN = re.compile(
    r"(?<![\w.-])(?:pytest|tox|nox|"
    r"python\s+-m\s+(?:pytest|unittest)|"
    r"npm\s+(?:run\s+)?test|pnpm\s+(?:run\s+)?test|"
    r"yarn\s+(?:run\s+)?test|bun\s+(?:run\s+)?test|"
    r"go\s+test|cargo\s+test|mvn\s+test|"
    r"gradle\s+test|dotnet\s+test|make\s+test|"
    r"deno\s+test|swift\s+test|mix\s+test|rebar3\s+eunit|"
    r"stack\s+test|cabal\s+test|phpunit|rspec|"
    r"bundle\s+exec\s+rspec|composer\s+test)(?![\w.-])",
    re.IGNORECASE,
)
SETUP_COMMAND_PATTERN = re.compile(
    r"(?<![\w.-])(?:python\s+-m\s+pip\s+install|uv\s+(?:sync|pip\s+install)|"
    r"pip\s+install|npm\s+(?:ci|install)|pnpm\s+install|yarn\s+install|"
    r"bun\s+install|bundle\s+install|poetry\s+install|pipenv\s+install|"
    r"composer\s+install|mix\s+deps\.get|rebar3\s+get-deps|"
    r"stack\s+setup|cabal\s+update|swift\s+package\s+resolve|"
    r"deno\s+install|"
    r"go\s+mod\s+download|cargo\s+build|mvn\s+install|"
    r"gradle\s+build|dotnet\s+restore)(?![\w.-])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Evidence:
    path: str
    line: int
    text: str


@dataclass(frozen=True)
class Finding:
    title: str
    detail: str
    evidence: Evidence
    command: str | None = None


@dataclass(frozen=True)
class Analysis:
    setup_steps: list[Finding]
    test_commands: list[Finding]
    contribution_guidance: list[Finding]
    starter_tasks: list[Finding]
    warnings: list[str]
    source_url: str | None = None
    source_ref: str | None = None


def _is_sensitive(path: Path) -> bool:
    name = path.name.lower()
    if name in SENSITIVE_NAMES or name.startswith(".env"):
        return True
    return any(part in name for part in SECRET_NAME_PARTS)


def _is_documentation(path: Path) -> bool:
    name = path.name.lower()
    return (
        name.startswith("readme")
        or name.startswith("contributing")
        or name in {"install.md", "installation.md", "setup.md"}
        or "docs" in path.parts
    )


def _is_contribution_file(path: Path) -> bool:
    name = path.name.lower()
    return name.startswith("contributing") or name in {
        "code_of_conduct.md",
        "development.md",
    }


def _path_parts(path: Path) -> set[str]:
    return {part.lower() for part in path.parts}


def _is_starter_task_path(path: Path) -> bool:
    return not (_path_parts(path) & TASK_EXCLUDED_DIRS)


def _iter_candidate_files(root: Path, warnings: list[str]):
    visited = 0

    def record_walk_error(error: OSError) -> None:
        warnings.append(f"Could not inspect a repository path: {error}")

    for current, directories, filenames in os.walk(
        root, topdown=True, followlinks=False, onerror=record_walk_error
    ):
        current_path = Path(current)
        directories[:] = sorted(
            directory
            for directory in directories
            if directory.lower() not in SKIP_DIRS
            and not (current_path / directory).is_symlink()
        )
        for filename in sorted(filenames):
            path = current_path / filename
            relative_path = path.relative_to(root)
            if (
                path.is_symlink()
                or _is_sensitive(path)
                or _path_parts(relative_path) & SKIP_DIRS
            ):
                continue
            if not (
                _is_documentation(path)
                or filename in MANIFEST_NAMES
                or path.suffix.lower() in SOURCE_EXTENSIONS
                or path.parts[-3:-1] == (".github", "workflows")
            ):
                continue
            if visited >= MAX_FILES:
                warnings.append(
                    f"Stopped after inspecting {MAX_FILES} candidate files."
                )
                return
            visited += 1
            try:
                if path.stat().st_size > MAX_FILE_SIZE:
                    warnings.append(
                        f"Skipped oversized file: {path.relative_to(root).as_posix()}"
                    )
                    continue
                content = path.read_bytes()
            except OSError as error:
                warnings.append(
                    f"Could not read {path.relative_to(root).as_posix()}: {error}"
                )
                continue
            if b"\0" in content:
                continue
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                warnings.append(
                    f"Skipped non-UTF-8 file: {path.relative_to(root).as_posix()}"
                )
                continue
            yield path, text.splitlines()


def _evidence(root: Path, path: Path, line_number: int, text: str) -> Evidence:
    return Evidence(
        path=path.relative_to(root).as_posix(),
        line=line_number,
        text=text.strip()[:300],
    )


def _command_from_line(line: str, pattern: re.Pattern[str]) -> str:
    match = pattern.search(line)
    if match is None:
        return line.strip("` ")
    opening_backtick = line.rfind("`", 0, match.start())
    if opening_backtick >= 0:
        closing_backtick = line.find("`", match.end())
        if closing_backtick >= 0:
            return line[opening_backtick + 1 : closing_backtick].strip()

    prefix = line[: match.start()].strip(" -*`:")
    if prefix and not re.fullmatch(r"(?:PS\s+)?[\w.\\/:<>-]+", prefix):
        return match.group().strip()

    command = line[match.start() :].strip()
    command = re.split(r"\s+#|;\s*|\.\s", command, maxsplit=1)[0]
    command = re.sub(r"\s+(?:and|then|to)\s+.*$", "", command)
    command = command.rstrip("` ,;")
    if command.endswith(".") and not re.search(r"\s\.$", command):
        command = command[:-1]
    return command.strip()


def analyze_repository(repository: str | Path) -> Analysis:
    """Inspect a local repository and return findings with source locations."""
    root = Path(repository).expanduser().resolve()
    if not root.exists():
        raise ValueError(f"Repository path does not exist: {root}")
    if not root.is_dir():
        raise ValueError(f"Repository path is not a directory: {root}")

    setup_steps: list[Finding] = []
    test_commands: list[Finding] = []
    contribution_guidance: list[Finding] = []
    starter_tasks: list[Finding] = []
    warnings: list[str] = []
    seen_tests: set[tuple[str, str]] = set()
    seen_setup: set[tuple[str, str]] = set()

    for path, lines in _iter_candidate_files(root, warnings):
        is_documentation = _is_documentation(path)
        is_contribution_file = _is_contribution_file(path)
        is_workflow = path.parts[-3:-1] == (".github", "workflows")
        is_test_config = is_documentation or path.name in MANIFEST_NAMES or is_workflow
        for line_number, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            setup_match = SETUP_COMMAND_PATTERN.search(line) if is_documentation else None
            if setup_match and not re.search(
                r"\bpip\s+install\s+(?:--upgrade|-U)\s+pip\b",
                line,
                re.IGNORECASE,
            ):
                command = _command_from_line(line, SETUP_COMMAND_PATTERN)
                key = (path.as_posix(), command)
                if key not in seen_setup and len(setup_steps) < MAX_SECTION_FINDINGS:
                    seen_setup.add(key)
                    setup_steps.append(
                        Finding(
                            title="Setup command",
                            detail="Install/build command found in project documentation.",
                            evidence=_evidence(root, path, line_number, line),
                            command=command,
                        )
                    )

            if is_test_config and TEST_COMMAND_PATTERN.search(line):
                command = _command_from_line(line, TEST_COMMAND_PATTERN)
                key = (path.as_posix(), command)
                if key not in seen_tests and len(test_commands) < MAX_SECTION_FINDINGS:
                    seen_tests.add(key)
                    test_commands.append(
                        Finding(
                            title="Test command",
                            detail="Test command found in project documentation or configuration.",
                            evidence=_evidence(root, path, line_number, line),
                            command=command,
                        )
                    )

            if is_contribution_file and re.search(
                r"\b(?:fork|clone|branch|pull request|commit|push|read|create|"
                r"install|run|verify|open|ensure|submit|follow|copy|configure|"
                r"must|should)\b",
                line,
                re.IGNORECASE,
            ):
                if len(contribution_guidance) < MAX_CONTRIBUTION_FINDINGS:
                    contribution_guidance.append(
                        Finding(
                            title="Contribution guidance",
                            detail="Relevant contribution instructions.",
                            evidence=_evidence(root, path, line_number, line),
                        )
                    )

            if (
                path.suffix.lower() in SOURCE_EXTENSIONS
                and _is_starter_task_path(path.relative_to(root))
            ):
                todo_match = TODO_PATTERN.search(line)
                if todo_match and len(starter_tasks) < MAX_STARTER_TASKS:
                    description = todo_match.group(2).strip()
                    starter_tasks.append(
                        Finding(
                            title=description or f"Review {todo_match.group(1).upper()}",
                            detail=(
                                "Potential starter task from an explicit TODO/FIXME/XXX "
                                "marker. Confirm scope and context before starting."
                            ),
                            evidence=_evidence(root, path, line_number, line),
                        )
                    )

    return Analysis(
        setup_steps=setup_steps,
        test_commands=test_commands,
        contribution_guidance=contribution_guidance,
        starter_tasks=starter_tasks,
        warnings=warnings,
    )
