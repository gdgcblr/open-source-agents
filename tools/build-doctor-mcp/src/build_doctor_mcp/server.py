"""BuildDoctor MCP server with read-only, bounded evidence tools."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("build-doctor")

_MANIFESTS = (
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "go.mod",
    "Cargo.toml",
    "composer.json",
    "mix.exs",
)
_MAX_FILE_BYTES = int(os.getenv("BUILD_DOCTOR_MAX_FILE_BYTES", "200000"))


def _evidence_lines(log: str) -> list[str]:
    return [
        line.strip()
        for line in log.splitlines()
        if re.search(r"(\[error\]|\berror:|\bfailed\b|\bfailure\b|tests run:)", line, re.I)
    ][:8]


def _diagnosis(log: str) -> dict[str, Any]:
    evidence = _evidence_lines(log)
    if not log.strip():
        return {
            "failure_type": "unknown",
            "summary": "No failure output was provided.",
            "confidence": "low",
            "evidence": [],
            "next_steps": ["Provide the complete relevant build, test, runtime, or API output."],
            "verification_status": "pending",
        }

    patterns = (
        (
            "compilation",
            re.compile(r"compilation error|cannot find symbol|syntax error|type error|failed to compile", re.I),
            "The output contains a compilation failure.",
            "high",
            ["Inspect the first compiler error and its source location.", "Check the referenced symbol and language configuration."],
        ),
        (
            "dependency-resolution",
            re.compile(r"could not resolve dependencies|module not found|no matching distribution|failed to fetch|package .* not found", re.I),
            "The project could not resolve or download a dependency.",
            "high",
            ["Inspect dependency names, versions, lockfiles, and configured registries.", "Check registry access and package availability."],
        ),
        (
            "test-failure",
            re.compile(r"tests run:.*(failures|errors): [1-9]|assertionerror|tests? failed|expected .* but was", re.I),
            "The output indicates that at least one test failed.",
            "moderate",
            ["Isolate the failing test and compare expected versus actual values.", "Rerun the targeted test after a change; verification is pending until then."],
        ),
        (
            "runtime-or-api",
            re.compile(r"(http|status|response).*(401|403|404|408|429|5\d\d)|timeout|connection refused|traceback|exception", re.I),
            "The output indicates a runtime or API interaction failure.",
            "moderate",
            ["Inspect the request, response status, timeout, and service logs.", "Check configuration and authentication without exposing credentials."],
        ),
    )
    for failure_type, pattern, summary, confidence, next_steps in patterns:
        if pattern.search(log):
            return {
                "failure_type": failure_type,
                "summary": summary,
                "confidence": confidence,
                "evidence": evidence,
                "next_steps": next_steps,
                "verification_status": "pending",
            }

    return {
        "failure_type": "unknown",
        "summary": "The supplied output does not match a supported failure signature.",
        "confidence": "low",
        "evidence": evidence,
        "next_steps": ["Provide the first error and its surrounding context."],
        "verification_status": "pending",
    }


def _safe_root(project_path: str) -> Path | None:
    root = Path(project_path).expanduser().resolve()
    return root if root.is_dir() else None


@mcp.tool()
def analyze_failure(log: str) -> str:
    """Classify supplied failure output and return evidence-linked next steps as JSON."""
    return json.dumps(_diagnosis(log), indent=2)


@mcp.tool()
def inspect_project(project_path: str) -> str:
    """Read bounded metadata from recognized project manifests without executing code."""
    root = _safe_root(project_path)
    if root is None:
        return json.dumps({"error": "project_path must point to an existing directory"})

    manifests: list[str] = []
    sections: list[str] = []
    for name in _MANIFESTS:
        path = root / name
        if not path.is_file() or path.is_symlink():
            continue
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                sections.append(f"--- {name} ---\n[file skipped: exceeds size limit]")
                manifests.append(name)
                continue
            sections.append(f"--- {name} ---\n{path.read_text(encoding='utf-8', errors='replace')[:_MAX_FILE_BYTES]}")
            manifests.append(name)
        except OSError as exc:
            sections.append(f"--- {name} ---\n[file unavailable: {exc}]")

    return json.dumps({"project_path": str(root), "manifests": manifests, "content": "\n\n".join(sections)}, indent=2)


@mcp.tool()
def summarize_diagnosis(log: str, project_path: str = "") -> str:
    """Combine failure analysis and optional manifest evidence into one JSON response."""
    project = json.loads(inspect_project(project_path)) if project_path else {"manifests": [], "content": ""}
    return json.dumps({"diagnosis": _diagnosis(log), "project": project}, indent=2)


def main() -> None:
    """Start the MCP server over stdio for MCP-compatible clients."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
