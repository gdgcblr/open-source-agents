"""Portable, versioned record of a single bounded reproduction attempt."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from .sandbox import TestResult


def repository_revision(repo: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True,
            text=True, timeout=3, shell=False, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and len(value) == 40 else None


def make_capsule(
    repo: Path, report: str, result: TestResult, analysis: str = "", *,
    execution_mode: str = "container",
) -> dict:
    if execution_mode not in {"container", "local_demo"}:
        raise ValueError("execution_mode must be 'container' or 'local_demo'.")
    isolated = execution_mode == "container"
    return {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "repository_revision": repository_revision(repo),
        "issue_sha256": hashlib.sha256(report.encode("utf-8")).hexdigest(),
        "analysis": analysis[:2000],
        "execution": {
            "mode": execution_mode,
            "status": result.status,
            "exit_code": result.exit_code,
            "command": list(result.command),
            "image": result.image,
            "network": "disabled" if isolated else "host-default",
            "repository_mount": "read-only" if isolated else "temporary-demo-fixture",
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    }


def save_capsule(capsule: dict, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(capsule, indent=2) + "\n", encoding="utf-8")


def load_capsule(source: Path) -> dict:
    data = json.loads(source.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("execution"), dict):
        raise ValueError("Unsupported or malformed capsule (expected schema_version 1).")
    revision = data.get("repository_revision")
    if revision is not None and (
        not isinstance(revision, str)
        or len(revision) != 40
        or any(character not in "0123456789abcdef" for character in revision.lower())
    ):
        raise ValueError("Capsule repository_revision must be a 40-character Git SHA or null.")
    # A capsule is evidence, never authority to choose a command or image.
    expected = ["python", "-m", "unittest", "discover", "-v"]
    execution = data["execution"]
    if execution.get("mode", "container") != "container":
        raise ValueError("Local demo capsules are not replayable; only container execution capsules can be replayed.")
    if execution.get("command") != expected or execution.get("image") != "python:3.12-slim":
        raise ValueError("Capsule command/image does not match the safe fixed runner.")
    return data
