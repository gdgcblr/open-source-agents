"""Build and test failure diagnosis engine for DevGuard.

Runs failing commands through the policy manager, extracts errors and tracebacks,
redacts secrets, and produces structured diagnostic reports distinguishing
observed evidence from AI hypotheses.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from devguard.ai_provider import AIProvider
from devguard.redact import redact_secrets
from devguard.runner import CommandResult


MAX_DIAGNOSTIC_OUTPUT_CHARS = 8000

DIAGNOSTIC_PROMPT_TEMPLATE = """You are a senior systems engineer assisting a developer with a build or test failure.
Analyze the following command output and return a JSON object with your findings.

Command: {command}
Exit Code: {exit_code}
Duration: {duration_ms}ms
Timed Out: {timed_out}

Command Output (sanitized):
{output}

Instructions:
1. Distinguish observed facts/errors from hypotheses.
2. Return a valid JSON object with EXACTLY these four keys:
   - "observed_errors": list of specific error messages directly visible in the output
   - "likely_causes": list of plausible hypotheses explaining why this failed
   - "suggested_diagnostic_steps": list of safe inspection or debugging commands to run
   - "potential_fixes": list of potential code or configuration fixes (label as unverified)
3. Return ONLY the JSON object. Do not wrap in markdown or prose.
"""


@dataclass
class DiagnosticReport:
    """Structured failure diagnosis report."""
    command: list[str]
    exit_code: int
    duration_ms: float
    timed_out: bool
    observed_errors: list[str] = field(default_factory=list)
    traceback_locations: list[str] = field(default_factory=list)
    likely_causes: list[str] = field(default_factory=list)
    suggested_diagnostic_steps: list[str] = field(default_factory=list)
    potential_fixes: list[str] = field(default_factory=list)
    source: str = "offline-rule-based"
    disclaimer: str = (
        "Notice: Diagnostic causes and potential fixes are hypotheses and recommendations. "
        "They have not been independently verified. Do not execute commands or apply fixes without verification."
    )


def extract_traceback_locations(output: str) -> list[str]:
    """Extract source file and line locations from output."""
    locations: list[str] = []

    # Python traceback pattern: File "...", line X
    py_matches = re.findall(r'File "([^"]+)", line (\d+)', output)
    for fpath, lno in py_matches:
        loc = f"{fpath}:{lno}"
        if loc not in locations:
            locations.append(loc)

    # Compiler/linter pattern: file.ext:line:col: error
    gcc_matches = re.findall(r'(\S+):(\d+):(?:\d+:)?\s*(?:error|fatal error):', output)
    for fpath, lno in gcc_matches:
        loc = f"{fpath}:{lno}"
        if loc not in locations:
            locations.append(loc)

    # Node.js stack trace: at ... (file:line:col)
    node_matches = re.findall(r'at\s+.*?\((.*?):(\d+):\d+\)', output)
    for fpath, lno in node_matches:
        loc = f"{fpath}:{lno}"
        if loc not in locations:
            locations.append(loc)

    return locations[:10]


def extract_observed_errors(output: str) -> list[str]:
    """Deterministically extract clear error lines from output."""
    errors: list[str] = []
    lines = output.splitlines()

    for line in lines:
        line_s = line.strip()
        if not line_s:
            continue
        if any(kw in line_s for kw in ["Error", "Exception", "FAILED", "AssertionError", "ImportError", "SyntaxError", "FAIL "]):
            clean = line_s[4:].strip() if line_s.startswith("E   ") else line_s
            if clean and clean not in errors:
                errors.append(clean)

    return errors[:10]


def generate_deterministic_diagnosis(
    command: list[str],
    result: CommandResult,
    duration_ms: float,
    timed_out: bool,
    sanitized_output: str,
) -> DiagnosticReport:
    """Produce a deterministic, rule-based diagnostic report without AI calls."""
    errors = extract_observed_errors(sanitized_output)
    locations = extract_traceback_locations(sanitized_output)

    likely_causes: list[str] = []
    suggested_steps: list[str] = []
    potential_fixes: list[str] = []

    if timed_out:
        likely_causes.append("Command execution exceeded the configured timeout limit.")
        suggested_steps.append("Check for infinite loops, deadlocks, or long-running network operations.")
        potential_fixes.append("Increase timeout configuration or optimize slow operations.")
    elif result.exit_code == 127:
        exe = command[0] if command else "binary"
        likely_causes.append(f"Executable '{exe}' was not found on system PATH.")
        suggested_steps.append(f"Run 'which {exe}' or check virtual environment installation.")
        potential_fixes.append(f"Install '{exe}' and ensure it is available in your PATH.")
    elif any("ModuleNotFoundError" in e or "ImportError" in e for e in errors):
        likely_causes.append("A required module or dependency is missing from the environment.")
        suggested_steps.append("Inspect dependency manifests (requirements.txt, pyproject.toml, package.json).")
        potential_fixes.append("Install missing dependencies into the active virtual environment.")
    else:
        likely_causes.append(f"Command terminated with non-zero exit code ({result.exit_code}).")
        if locations:
            suggested_steps.append(f"Inspect the failing source location: {locations[0]}")
        suggested_steps.append("Run the command with verbose logging enabled (e.g. -vv or --verbose).")
        potential_fixes.append("Resolve observed exceptions and check recent code changes against test expectations.")

    return DiagnosticReport(
        command=command,
        exit_code=result.exit_code,
        duration_ms=round(duration_ms, 2),
        timed_out=timed_out,
        observed_errors=errors or ["Non-zero exit code with no explicit exception signature."],
        traceback_locations=locations,
        likely_causes=likely_causes,
        suggested_diagnostic_steps=suggested_steps,
        potential_fixes=potential_fixes,
        source="offline-rule-based",
    )


def diagnose_failure(
    command: list[str],
    result: CommandResult,
    duration_ms: float,
    timed_out: bool = False,
    provider: AIProvider | None = None,
) -> DiagnosticReport:
    """Analyze a failed command execution and generate a structured report.

    Args:
        command: Command argument list.
        result: CommandResult from subprocess execution.
        duration_ms: Execution duration in milliseconds.
        timed_out: Whether the execution timed out.
        provider: Optional AIProvider for advanced root-cause hypothesis generation.

    Returns:
        Structured DiagnosticReport.
    """
    raw_output = (result.stdout or "") + "\n" + (result.stderr or "")

    # CRITICAL: Redact secrets before any processing or model requests
    sanitized = redact_secrets(raw_output)

    # Bound output size to avoid memory and token limits
    if len(sanitized) > MAX_DIAGNOSTIC_OUTPUT_CHARS:
        sanitized = (
            sanitized[:MAX_DIAGNOSTIC_OUTPUT_CHARS // 2]
            + "\n\n... [output truncated for diagnostics] ...\n\n"
            + sanitized[-(MAX_DIAGNOSTIC_OUTPUT_CHARS // 2):]
        )

    # Deterministic baseline analysis
    deterministic = generate_deterministic_diagnosis(
        command=command,
        result=result,
        duration_ms=duration_ms,
        timed_out=timed_out,
        sanitized_output=sanitized,
    )

    if provider is None:
        return deterministic

    try:
        prompt = DIAGNOSTIC_PROMPT_TEMPLATE.format(
            command=" ".join(command),
            exit_code=result.exit_code,
            duration_ms=round(duration_ms, 2),
            timed_out=timed_out,
            output=sanitized,
        )

        resp_text = provider.generate(prompt).strip()
        # Clean any markdown code blocks
        clean_json = re.sub(r"^```[a-zA-Z]*\n?", "", resp_text)
        clean_json = re.sub(r"\n?```$", "", clean_json).strip()

        data = json.loads(clean_json)

        return DiagnosticReport(
            command=command,
            exit_code=result.exit_code,
            duration_ms=round(duration_ms, 2),
            timed_out=timed_out,
            observed_errors=data.get("observed_errors") or deterministic.observed_errors,
            traceback_locations=deterministic.traceback_locations,
            likely_causes=data.get("likely_causes") or deterministic.likely_causes,
            suggested_diagnostic_steps=data.get("suggested_diagnostic_steps") or deterministic.suggested_diagnostic_steps,
            potential_fixes=data.get("potential_fixes") or deterministic.potential_fixes,
            source=f"ai-assisted ({getattr(provider, 'name', 'ai')})",
        )
    except Exception:
        # Fall back cleanly to deterministic analysis on provider error
        return deterministic
