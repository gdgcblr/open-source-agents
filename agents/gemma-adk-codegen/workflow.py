"""Data validation helpers for the Gemma ADK code-generation workflow."""

from __future__ import annotations

import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

MAX_PLAN_CHARS = 32_000
MAX_AGENT_RESPONSE_CHARS = 40_000
MAX_TITLE_CHARS = 160
MAX_DESCRIPTION_CHARS = 4_000
MAX_CRITERIA = 12
MAX_CRITERION_CHARS = 500
MAX_TOTAL_TASK_CHARS = 24_000
MAX_FILE_COUNT = 30
MAX_FILE_PATH_CHARS = 180
MAX_FILE_CHARS = 20_000
MAX_PROJECT_CHARS = 100_000


def validate_problem(problem: str, max_chars: int = 12_000) -> str:
    """Validate user input size and reject empty or control-only input."""
    normalized = problem.strip()
    if not normalized:
        raise ValueError("Problem statement must not be empty.")
    if len(normalized) > max_chars:
        raise ValueError(f"Problem statement exceeds the {max_chars}-character limit.")
    if not any(character.isprintable() for character in normalized):
        raise ValueError("Problem statement must contain printable text.")
    return normalized


def validate_agent_response(response: str) -> str:
    """Reject unexpectedly large model responses before writing artifacts."""
    if len(response) > MAX_AGENT_RESPONSE_CHARS:
        raise ValueError(
            f"Agent response exceeds the {MAX_AGENT_RESPONSE_CHARS}-character limit."
        )
    if not response.strip():
        raise ValueError("Agent response must not be empty.")
    return response.strip()


def encode_untrusted(value: Any) -> str:
    """Serialize untrusted context to make its data boundary explicit in prompts."""
    return json.dumps(value, ensure_ascii=True)


def parse_generated_files(response: str) -> list[dict[str, str]]:
    """Parse a coding agent's JSON file manifest and reject unsafe paths."""
    response = validate_agent_response(response)
    candidate = response
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, re.DOTALL | re.IGNORECASE)
    if fenced:
        candidate = fenced.group(1)
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Coding agent must return a JSON file manifest: {exc.msg}") from exc

    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, list) or not files:
        raise ValueError("Coding agent response must contain a non-empty 'files' list.")
    if len(files) > MAX_FILE_COUNT:
        raise ValueError(f"Coding agent returned more than {MAX_FILE_COUNT} files.")

    validated: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    total_chars = 0
    for index, file_entry in enumerate(files, start=1):
        if not isinstance(file_entry, dict):
            raise ValueError(f"Generated file {index} must be a JSON object.")
        path = file_entry.get("path")
        content = file_entry.get("content")
        if not isinstance(path, str) or not path.strip():
            raise ValueError(f"Generated file {index} is missing a path.")
        if not isinstance(content, str):
            raise ValueError(f"Generated file {index} content must be a string.")
        normalized = path.replace("\\", "/")
        parts = normalized.split("/")
        if (
            len(normalized) > MAX_FILE_PATH_CHARS
            or normalized.startswith("/")
            or re.match(r"^[A-Za-z]:", normalized)
            or any(part in {"", ".", ".."} for part in parts)
            or "\x00" in normalized
        ):
            raise ValueError(f"Generated file {index} has an unsafe relative path.")
        if any(part.lower() == ".git" for part in parts) or parts[0].lower() == ".env":
            raise ValueError(f"Generated file {index} targets a protected path.")
        path_key = normalized.casefold()
        if path_key in seen_paths:
            raise ValueError(f"Coding agent returned duplicate path: {normalized}")
        if len(content) > MAX_FILE_CHARS:
            raise ValueError(f"Generated file {normalized} exceeds {MAX_FILE_CHARS} characters.")
        seen_paths.add(path_key)
        total_chars += len(content)
        validated.append({"path": normalized, "content": content})

    if total_chars > MAX_PROJECT_CHARS:
        raise ValueError(f"Generated project exceeds {MAX_PROJECT_CHARS} characters.")
    return validated


def write_generated_files(project_dir: "Path", files: list[dict[str, str]]) -> list[str]:
    """Write validated project files without following symlinked parent paths."""
    root = project_dir.resolve()
    written: list[str] = []
    for entry in files:
        relative = Path(entry["path"])
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        resolved_parent = destination.parent.resolve()
        if resolved_parent != root and root not in resolved_parent.parents:
            raise ValueError(f"Generated path escapes project directory: {entry['path']}")
        if destination.is_symlink():
            raise ValueError(f"Generated file must not replace a symlink: {entry['path']}")
        destination.write_text(entry["content"], encoding="utf-8")
        written.append(entry["path"])
    return written


def parse_task_plan(response: str, max_tasks: int) -> list[dict[str, Any]]:
    """Parse and validate a JSON task plan returned by the planning agent."""
    if len(response) > MAX_PLAN_CHARS:
        raise ValueError(f"Planner response exceeds the {MAX_PLAN_CHARS}-character limit.")
    candidate = response.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", candidate, re.DOTALL | re.IGNORECASE)
    if fenced:
        candidate = fenced.group(1)

    if not candidate.startswith("{"):
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Planner response did not contain a JSON object.")
        candidate = candidate[start : end + 1]

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Planner returned invalid JSON: {exc.msg}") from exc

    tasks = payload.get("tasks") if isinstance(payload, dict) else None
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("Task plan must contain a non-empty 'tasks' list.")
    if len(tasks) > max_tasks:
        raise ValueError(f"Planner returned {len(tasks)} tasks; maximum is {max_tasks}.")

    validated: list[dict[str, Any]] = []
    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, dict):
            raise ValueError(f"Task {index} must be a JSON object.")
        title = task.get("title")
        description = task.get("description")
        criteria = task.get("acceptance_criteria")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"Task {index} is missing a non-empty title.")
        if len(title) > MAX_TITLE_CHARS:
            raise ValueError(f"Task {index} title exceeds {MAX_TITLE_CHARS} characters.")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"Task {index} is missing a non-empty description.")
        if len(description) > MAX_DESCRIPTION_CHARS:
            raise ValueError(f"Task {index} description exceeds {MAX_DESCRIPTION_CHARS} characters.")
        if not isinstance(criteria, list) or not criteria or not all(
            isinstance(item, str) and item.strip() for item in criteria
        ):
            raise ValueError(f"Task {index} needs non-empty string acceptance criteria.")
        if len(criteria) > MAX_CRITERIA:
            raise ValueError(f"Task {index} has more than {MAX_CRITERIA} acceptance criteria.")
        if any(len(item) > MAX_CRITERION_CHARS for item in criteria):
            raise ValueError(
                f"Task {index} acceptance criteria must not exceed {MAX_CRITERION_CHARS} characters each."
            )
        validated.append(
            {
                "id": f"task-{index:03d}",
                "title": title.strip(),
                "description": description.strip(),
                "acceptance_criteria": [item.strip() for item in criteria],
            }
        )
    total_chars = sum(
        len(task["title"])
        + len(task["description"])
        + sum(len(item) for item in task["acceptance_criteria"])
        for task in validated
    )
    if total_chars > MAX_TOTAL_TASK_CHARS:
        raise ValueError(f"Task plan exceeds the {MAX_TOTAL_TASK_CHARS}-character content limit.")
    return validated


def safe_slug(value: str) -> str:
    """Convert a task title to a filesystem-safe, readable slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:60].strip("-") or "task"


def project_display_name(proposed_name: str | None, problem: str) -> str:
    """Return a concise display name, falling back to the user's problem statement."""
    candidate = proposed_name.strip() if isinstance(proposed_name, str) else ""
    if candidate:
        candidate = re.sub(r"[\x00-\x1f\x7f]", " ", candidate)
        candidate = re.sub(r"\s+", " ", candidate).strip(" .-_")
        if candidate:
            return candidate[:80]

    fallback = re.split(r"[.!?\n]", problem, maxsplit=1)[0].strip()
    fallback = re.sub(r"^(please\s+)?(build|create|make|develop|implement)\s+", "", fallback, flags=re.I)
    fallback = re.sub(r"^(me\s+)?(a|an|the)\s+", "", fallback, flags=re.I)
    fallback = re.sub(r"\s+", " ", fallback).strip(" .-_ ")
    return (fallback[:80] or "Generated Project").title()