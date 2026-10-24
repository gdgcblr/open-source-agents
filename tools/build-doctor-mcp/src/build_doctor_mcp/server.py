"""Read-only BuildDoctor MCP server with bounded, redacted diagnostics."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("build-doctor")
SCHEMA_VERSION = "1.0"
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
_MAX_FILE_BYTES = min(max(int(os.getenv("BUILD_DOCTOR_MAX_FILE_BYTES", "200000")), 1), 1000000)
_MAX_LOG_CHARS = min(max(int(os.getenv("BUILD_DOCTOR_MAX_LOG_CHARS", "200000")), 1), 1000000)
_SECRET_PATTERNS = (
    (re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(api[_-]?key|token|password|secret|client_secret)\s*[:=]\s*[^\s,;]+"), r"\1=[REDACTED]"),
    (re.compile(r"(?i)(-----BEGIN [A-Z ]+ PRIVATE KEY-----).*?(-----END [A-Z ]+ PRIVATE KEY-----)", re.S), r"\1[REDACTED]\2"),
)


def _redact(text: str) -> str:
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _bounded_log(log: str) -> tuple[str, bool]:
    redacted = _redact(log or "")
    return redacted[:_MAX_LOG_CHARS], len(redacted) > _MAX_LOG_CHARS


def _evidence_lines(log: str) -> list[str]:
    return [
        line.strip()
        for line in log.splitlines()
        if re.search(r"(\[error\]|\berror:|\bfailed\b|\bfailure\b|tests run:|\bexception\b)", line, re.I)
    ][:8]


def _result(
    failure_type: str,
    summary: str,
    confidence: str,
    evidence: list[str],
    root_causes: list[str],
    remediation: list[str],
    missing_evidence: list[str],
    truncated: bool = False,
) -> dict[str, Any]:
    hypothesis = {
        "id": "H1",
        "statement": root_causes[0],
        "confidence": confidence,
        "supporting_evidence": evidence,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "failure_type": failure_type,
        "summary": summary,
        "confidence": confidence,
        "evidence": evidence,
        "hypotheses": [hypothesis],
        "root_causes": root_causes,
        "remediation_plan": remediation,
        "missing_evidence": missing_evidence,
        "verification": {
            "status": "pending",
            "reason": "No post-change build, test, or runtime result was supplied.",
            "safe_check": remediation[-1] if remediation else "Rerun the smallest relevant check after review.",
        },
        "verification_status": "pending",
        "input_truncated": truncated,
        "guardrails": [
            "Read-only analysis; no commands, network calls, file writes, or automatic fixes.",
            "Evidence is redacted before it is returned to the client.",
        ],
    }


def _diagnosis(log: str) -> dict[str, Any]:
    bounded, truncated = _bounded_log(log)
    if not bounded.strip():
        return _result(
            "unknown",
            "No failure output was provided.",
            "low",
            [],
            ["There is insufficient evidence to identify a root cause."],
            ["Provide the complete relevant build, test, runtime, or API output."],
            ["The first error and surrounding context are missing."],
            truncated,
        )

    evidence = _evidence_lines(bounded)
    patterns = (
        (
            "compilation",
            re.compile(r"compilation error|cannot find symbol|syntax error|type error|failed to compile", re.I),
            "The output contains a compilation failure.",
            "high",
            ["A source or compiler configuration issue is likely; the exact symbol and location need confirmation."],
            ["Inspect the first compiler error and its source location.", "Check the referenced symbol, language configuration, and compiler settings.", "Rerun the smallest compilation check after the change."],
            ["The affected source file and compiler command are not present."],
        ),
        (
            "dependency-resolution",
            re.compile(r"could not resolve dependencies|module not found|no matching distribution|failed to fetch|package .* not found", re.I),
            "The project could not resolve or download a dependency.",
            "high",
            ["A dependency name, version, lockfile, registry, or network-access issue may be blocking resolution."],
            ["Inspect dependency names, versions, lockfiles, and configured registries.", "Check registry access and package availability without exposing credentials.", "Rerun dependency resolution after confirming the configuration."],
            ["The dependency manifest, lockfile, and registry response are not present."],
        ),
        (
            "test-failure",
            re.compile(r"tests run:.*(failures|errors): [1-9]|assertionerror|tests? failed|expected .* but was", re.I),
            "The output indicates that at least one test failed.",
            "moderate",
            ["The observed assertion or test result is evidence of a failing behavior, not proof of its underlying cause."],
            ["Isolate the failing test and compare expected versus actual values.", "Inspect the test report, fixture, and environment-dependent inputs.", "Rerun the targeted test after a change; verification remains pending until then."],
            ["The failing test name, stack trace, and expected/actual values are incomplete."],
        ),
        (
            "runtime-or-api",
            re.compile(r"(http|status|response).*(401|403|404|408|429|5\d\d)|timeout|connection refused|traceback|exception", re.I),
            "The output indicates a runtime or API interaction failure.",
            "moderate",
            ["The runtime or response signal is observable, but the service configuration and request context are needed to separate causes."],
            ["Inspect request method, response status, timeout, correlation ID, and service logs.", "Check endpoint configuration and authentication without exposing credentials.", "Repeat a safe, read-only health check after confirming the configuration."],
            ["The sanitized request, response body, service logs, and environment are incomplete."],
        ),
    )
    for failure_type, pattern, summary, confidence, causes, remediation, missing in patterns:
        if pattern.search(bounded):
            return _result(failure_type, summary, confidence, evidence, causes, remediation, missing, truncated)

    return _result(
        "unknown",
        "The supplied output does not match a supported failure signature.",
        "low",
        evidence,
        ["The available evidence is insufficient or represents an unsupported failure format."],
        ["Provide the first error and its surrounding context.", "Identify the command, runtime, service, and expected outcome.", "Do not apply a change until the missing evidence is reviewed."],
        ["The command, environment, expected outcome, and first causal error are missing."],
        truncated,
    )


def _safe_root(project_path: str) -> Path | None:
    root = Path(project_path).expanduser().resolve()
    if not root.is_dir():
        return None
    allowed = os.getenv("BUILD_DOCTOR_ALLOWED_ROOT")
    if allowed:
        allowed_root = Path(allowed).expanduser().resolve()
        try:
            root.relative_to(allowed_root)
        except ValueError:
            return None
    return root


@mcp.tool()
def analyze_failure(log: str) -> str:
    """Classify sanitized failure output and return a versioned diagnostic contract as JSON."""
    return json.dumps(_diagnosis(log), indent=2)


@mcp.tool()
def inspect_project(project_path: str) -> str:
    """Read bounded, redacted metadata from root project manifests without executing code."""
    root = _safe_root(project_path)
    if root is None:
        return json.dumps({"schema_version": SCHEMA_VERSION, "error": "project_path is missing, invalid, or outside BUILD_DOCTOR_ALLOWED_ROOT"})

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
            content = _redact(path.read_text(encoding="utf-8", errors="replace")[:_MAX_FILE_BYTES])
            sections.append(f"--- {name} ---\n{content}")
            manifests.append(name)
        except OSError as exc:
            sections.append(f"--- {name} ---\n[file unavailable: {exc}]")

    return json.dumps({
        "schema_version": SCHEMA_VERSION,
        "project_path": str(root),
        "manifests": manifests,
        "content": "\n\n".join(sections),
        "guardrails": ["Root-level allowlisted manifests only; no symlinks, recursion, execution, or writes."],
    }, indent=2)


@mcp.tool()
def summarize_diagnosis(log: str, project_path: str = "") -> str:
    """Combine evidence-linked failure analysis and optional project metadata as JSON."""
    project = json.loads(inspect_project(project_path)) if project_path else {"schema_version": SCHEMA_VERSION, "manifests": [], "content": ""}
    return json.dumps({"schema_version": SCHEMA_VERSION, "diagnosis": _diagnosis(log), "project": project}, indent=2)


def main() -> None:
    """Start the MCP server over stdio for MCP-compatible clients."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
