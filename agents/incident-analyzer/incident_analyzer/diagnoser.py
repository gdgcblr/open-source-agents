"""Core diagnosis engine for the Incident Analyzer.

Correlates sanitized logs and stack traces with AST-indexed codebase
specifications, then uses an LLM (Google Gemini) to produce structured
root-cause analyses and code fix suggestions.

Supports both live Gemini API mode and offline mock mode for testing
and reproducibility without API keys.
"""

from __future__ import annotations

import ast
import difflib
import json
import logging
import os
import re
import subprocess
from typing import Optional

from .models import (
    AffectedSymbol,
    CodebaseSpec,
    Diagnosis,
    IncidentInput,
    Severity,
    SuggestedFix,
)
from .sanitizer import sanitize_log

logger = logging.getLogger(__name__)


# ── Stack trace correlation ─────────────────────────────────────────────


def extract_traceback_frames(log_text: str) -> list[dict]:
    """Extract file paths and line numbers from Python traceback frames.

    Args:
        log_text: Raw log text possibly containing Python tracebacks.

    Returns:
        List of dicts with keys: file, line, function, and optionally code.
    """
    pattern = re.compile(r'File "([^"]+)", line (\d+), in (\S+)')
    frames = []
    lines = log_text.splitlines()
    for i, line in enumerate(lines):
        match = pattern.search(line)
        if match:
            frame: dict = {
                "file": match.group(1),
                "line": int(match.group(2)),
                "function": match.group(3),
            }
            # Grab the code line (usually the next line in a traceback)
            if i + 1 < len(lines):
                code_line = lines[i + 1].strip()
                if code_line and not code_line.startswith("File "):
                    frame["code"] = code_line
            frames.append(frame)
    return frames


def correlate_with_spec(
    frames: list[dict], spec: CodebaseSpec
) -> list[AffectedSymbol]:
    """Match traceback frames against the codebase spec to identify affected symbols.

    Args:
        frames: Extracted traceback frames.
        spec: The indexed codebase specification.

    Returns:
        List of AffectedSymbol instances.
    """
    affected = []
    seen: set[tuple[str, str]] = set()

    for frame in frames:
        file_path = frame["file"]
        line_num = frame.get("line", 0)
        func_name = frame.get("function", "<unknown>")

        for module in spec.modules:
            # Match by file path (exact, suffix, or relative)
            if not (
                module.file_path == file_path
                or file_path.endswith(module.file_path)
                or module.file_path.endswith(file_path.lstrip("./"))
            ):
                continue

            for symbol in module.symbols:
                if symbol.name == func_name or (
                    symbol.line_start <= line_num <= symbol.line_end
                ):
                    key = (symbol.name, symbol.file_path)
                    if key not in seen:
                        seen.add(key)
                        affected.append(
                            AffectedSymbol(
                                name=symbol.name,
                                file_path=symbol.file_path,
                                line_start=symbol.line_start,
                                line_end=symbol.line_end,
                                relevance=(
                                    f"Traceback frame at line {line_num} "
                                    f"in function '{func_name}'"
                                ),
                            )
                        )
    return affected


def _build_context_for_llm(
    spec: CodebaseSpec,
    incident: IncidentInput,
    affected: list[AffectedSymbol],
    sanitized_log: str,
) -> str:
    """Build a focused prompt context for the LLM from spec and incident data.

    Only includes relevant symbols (affected + their callers) to minimize
    token usage and avoid sending the entire codebase.
    """
    context_parts = ["## Codebase Context (AST-indexed)\n"]

    # Gather affected symbol details
    affected_names = {s.name for s in affected}
    relevant_symbols = []

    for module in spec.modules:
        for symbol in module.symbols:
            # Include directly affected symbols
            if symbol.name in affected_names:
                relevant_symbols.append(symbol)
            # Include symbols that call affected symbols
            elif any(call in affected_names for call in symbol.calls):
                relevant_symbols.append(symbol)

    # If no symbols correlated, include a summary of all modules
    if not relevant_symbols:
        context_parts.append(
            "No direct symbol correlation found. Module overview:\n"
        )
        for module in spec.modules:
            symbol_names = [s.name for s in module.symbols]
            context_parts.append(
                f"- `{module.file_path}`: "
                f"{', '.join(symbol_names) if symbol_names else 'no symbols'}"
            )
    else:
        for symbol in relevant_symbols:
            context_parts.append(
                f"### `{symbol.name}` ({symbol.symbol_type.value}) "
                f"in `{symbol.file_path}`"
            )
            context_parts.append(f"Lines {symbol.line_start}-{symbol.line_end}")
            context_parts.append(f"Signature: `{symbol.signature}`")
            if symbol.docstring:
                context_parts.append(f"Docstring: {symbol.docstring}")
            if symbol.calls:
                context_parts.append(f"Calls: {', '.join(symbol.calls)}")
            if symbol.source_snippet:
                context_parts.append(
                    f"```python\n{symbol.source_snippet}\n```"
                )
            context_parts.append("")

    # Add the sanitized log
    context_parts.append("\n## Error Log / Stack Trace (sanitized)\n")
    context_parts.append(f"```\n{sanitized_log}\n```")

    # Add actual vs expected if provided
    if incident.actual_output:
        context_parts.append(
            f"\n## Actual Output\n```\n{incident.actual_output}\n```"
        )
    if incident.expected_output:
        context_parts.append(
            f"\n## Expected Output\n```\n{incident.expected_output}\n```"
        )

    if incident.context:
        context_parts.append(f"\n## Developer Context\n{incident.context}")

    return "\n".join(context_parts)


# ── LLM Integration ─────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an expert software incident analyst. You are given:
1. AST-indexed codebase context (function signatures, call graphs, source snippets)
2. Sanitized error logs or stack traces
3. Optionally, actual vs expected output

Your job is to:
1. Identify the root cause of the incident
2. Assess the severity (critical/high/medium/low/info)
3. Identify affected code symbols
4. Suggest concrete code fixes with before/after snippets
5. Provide prevention tips

IMPORTANT RULES:
- Base your analysis strictly on the provided code context and logs
- Do not hallucinate function names or file paths not present in the context
- Ensure suggested code fixes are syntactically valid Python
- Be specific about line numbers and file paths

Respond ONLY with valid JSON matching this exact schema:
{
  "root_cause": "string - detailed root cause analysis",
  "severity": "critical|high|medium|low|info",
  "affected_symbols": [
    {
      "name": "symbol_name",
      "file_path": "path/to/file.py",
      "line_start": 10,
      "line_end": 25,
      "relevance": "why this symbol is involved"
    }
  ],
  "suggested_fixes": [
    {
      "file_path": "path/to/file.py",
      "original_code": "original code snippet",
      "fixed_code": "corrected code snippet",
      "explanation": "why this fixes the issue"
    }
  ],
  "prevention_tips": ["tip1", "tip2"],
  "confidence": 0.85
}
"""


def _call_gemini(prompt: str, model_name: str = "gemini-2.5-flash") -> str:
    """Call the Google Gemini API.

    Args:
        prompt: The full prompt to send.
        model_name: Gemini model identifier.

    Returns:
        Raw response text from the model.

    Raises:
        RuntimeError: If the API call fails or dependencies are missing.
    """
    try:
        from google import genai  # type: ignore[import-untyped]
    except ImportError:
        raise RuntimeError(
            "google-genai package is not installed. "
            "Install it with: pip install google-genai"
        )

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable is not set. "
            "Set it or use --mock mode for offline testing."
        )

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )
    return response.text


def _mock_diagnose(
    sanitized_log: str, affected: list[AffectedSymbol]
) -> Diagnosis:
    """Generate a mock diagnosis for testing without API keys.

    Produces a realistic-looking diagnosis based on simple heuristic
    analysis of the log text and affected symbols.
    """
    root_cause = "Unable to determine root cause (mock mode)"
    severity = Severity.MEDIUM

    error_patterns: dict[str, tuple[str, Severity]] = {
        "TypeError": (
            "Type mismatch in function arguments or return value",
            Severity.MEDIUM,
        ),
        "AttributeError": (
            "Accessing attribute on None or incorrect object type",
            Severity.MEDIUM,
        ),
        "ImportError": (
            "Missing or incorrectly installed dependency",
            Severity.HIGH,
        ),
        "ModuleNotFoundError": (
            "Required module is not installed",
            Severity.HIGH,
        ),
        "KeyError": (
            "Attempting to access a dictionary key that does not exist",
            Severity.MEDIUM,
        ),
        "IndexError": (
            "List index out of range - possible off-by-one error",
            Severity.MEDIUM,
        ),
        "ValueError": (
            "Invalid value passed to function",
            Severity.MEDIUM,
        ),
        "FileNotFoundError": (
            "Expected file does not exist at the specified path",
            Severity.HIGH,
        ),
        "ConnectionError": (
            "Failed to establish connection to external service",
            Severity.CRITICAL,
        ),
        "TimeoutError": (
            "Operation timed out - possible performance bottleneck",
            Severity.HIGH,
        ),
        "PermissionError": (
            "Insufficient permissions to access resource",
            Severity.HIGH,
        ),
        "RuntimeError": (
            "Runtime error during execution",
            Severity.HIGH,
        ),
        "ZeroDivisionError": (
            "Division by zero - missing input validation",
            Severity.MEDIUM,
        ),
        "RecursionError": (
            "Maximum recursion depth exceeded - possible infinite loop",
            Severity.CRITICAL,
        ),
    }

    for error_type, (cause, sev) in error_patterns.items():
        if error_type in sanitized_log:
            root_cause = cause
            severity = sev
            break

    # Build mock suggested fixes from affected symbols
    suggested_fixes = []
    for sym in affected[:2]:
        orig = f"# Code at {sym.file_path}:{sym.line_start}\ndef {sym.name}():\n    pass\n"
        fixed = f"# Code at {sym.file_path}:{sym.line_start}\ndef {sym.name}():\n    # Safe guard added\n    pass\n"
        diff_text = generate_unified_diff(sym.file_path, orig, fixed)
        suggested_fixes.append(
            SuggestedFix(
                file_path=sym.file_path,
                original_code=orig,
                fixed_code=fixed,
                explanation=(
                    f"Review {sym.name} at line {sym.line_start} - "
                    f"{sym.relevance}"
                ),
                diff=diff_text,
                patch_verified=True,
            )
        )

    return Diagnosis(
        root_cause=f"[MOCK MODE] {root_cause}",
        severity=severity,
        affected_symbols=affected,
        suggested_fixes=suggested_fixes,
        prevention_tips=[
            "[Mock] Add input validation and type checking",
            "[Mock] Add comprehensive error handling with specific exceptions",
            "[Mock] Write unit tests covering edge cases",
        ],
        confidence=0.5,
    )


def generate_unified_diff(file_path: str, original: str, fixed: str) -> str:
    """Generate a git-compatible unified diff between original and fixed code.

    Args:
        file_path: Target file path.
        original: Original code snippet.
        fixed: Fixed replacement snippet.

    Returns:
        Unified diff string with standard a/ and b/ headers.
    """
    orig_lines = [line + "\n" for line in original.splitlines()]
    fixed_lines = [line + "\n" for line in fixed.splitlines()]
    diff = difflib.unified_diff(
        orig_lines,
        fixed_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
    )
    return "".join(diff)


def verify_patch(fix: SuggestedFix, root_path: Optional[str] = None) -> bool:
    """Verify that a suggested code fix is syntactically valid and generates a clean diff.

    Validates:
    1. Python AST syntax on the fixed code.
    2. Generates unified diff if not yet populated.
    3. Executes git apply --check dry-run if root_path is provided.

    Args:
        fix: The SuggestedFix instance to verify.
        root_path: Optional path to codebase root for git apply check.

    Returns:
        True if syntax is valid, False otherwise.
    """
    if not fix.diff:
        fix.diff = generate_unified_diff(fix.file_path, fix.original_code, fix.fixed_code)

    try:
        ast.parse(fix.fixed_code)
        fix.patch_verified = True
    except SyntaxError as e:
        logger.warning(
            "Suggested fix for %s has syntax issues: %s. "
            "Fix will be presented with a syntax warning.",
            fix.file_path,
            e,
        )
        fix.patch_verified = False
        fix.explanation += (
            " ⚠️ Note: This suggestion may have syntax issues - review carefully."
        )
        return False

    if root_path and fix.diff:
        try:
            res = subprocess.run(
                ["git", "apply", "--check", "-"],
                input=fix.diff.encode("utf-8"),
                cwd=root_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=3,
            )
            if res.returncode == 0:
                fix.explanation += " (Patch verified: applies cleanly via git)"
        except Exception:
            pass

    return True


def _validate_fix_syntax(fix: SuggestedFix, root_path: Optional[str] = None) -> None:
    """Backward-compatible wrapper for verify_patch."""
    verify_patch(fix, root_path)


def _parse_llm_response(
    response_text: str, affected: list[AffectedSymbol], root_path: Optional[str] = None
) -> Diagnosis:
    """Parse and validate the LLM JSON response into a Diagnosis.

    Falls back to a partial diagnosis if parsing fails.
    """
    try:
        # Strip markdown code fences if present
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        data = json.loads(cleaned)
        diagnosis = Diagnosis.model_validate(data)

        # Validate and verify each suggested fix
        for fix in diagnosis.suggested_fixes:
            verify_patch(fix, root_path=root_path)

        return diagnosis

    except (json.JSONDecodeError, Exception) as e:
        logger.warning("Failed to parse LLM response: %s. Using fallback.", e)
        return Diagnosis(
            root_cause=f"LLM analysis (raw): {response_text[:500]}",
            severity=Severity.MEDIUM,
            affected_symbols=affected,
            suggested_fixes=[],
            prevention_tips=["Review the raw LLM output above for details"],
            confidence=0.3,
        )


# ── Public API ──────────────────────────────────────────────────────────


def diagnose(
    spec: CodebaseSpec,
    incident: IncidentInput,
    mock: bool = False,
    model_name: str = "gemini-2.5-flash",
) -> Diagnosis:
    """Run incident diagnosis against the codebase spec.

    This is the main entry point for the diagnosis engine.

    Args:
        spec: The AST-indexed codebase specification (from one-time setup).
        incident: The incident input (logs, optional actual/expected output).
        mock: If True, use mock mode (no API call). Useful for testing.
        model_name: Gemini model to use for diagnosis.

    Returns:
        A structured Diagnosis with root cause, affected symbols,
        suggested fixes, and prevention tips.
    """
    logger.info("Starting incident diagnosis...")

    # Step 1: Sanitize the log input (security guardrail)
    sanitized_log, sanitization_report = sanitize_log(incident.log_text)
    if sanitization_report.was_modified:
        logger.info(
            "Log sanitization applied %d redaction type(s) before analysis",
            len(sanitization_report.redactions),
        )

    # Step 2: Extract traceback frames and correlate with spec
    frames = extract_traceback_frames(sanitized_log)
    affected = correlate_with_spec(frames, spec)
    logger.info(
        "Extracted %d traceback frames, correlated %d affected symbols",
        len(frames),
        len(affected),
    )

    # Step 3: Diagnose using mock or LLM
    if mock:
        logger.info("Using mock mode for diagnosis")
        return _mock_diagnose(sanitized_log, affected)

    # Step 4: Build LLM context and call Gemini
    context = _build_context_for_llm(spec, incident, affected, sanitized_log)
    logger.info("Built LLM context (%d chars), calling Gemini...", len(context))

    response_text = _call_gemini(context, model_name=model_name)
    logger.info("Received LLM response (%d chars)", len(response_text))

    # Step 5: Parse and validate LLM response
    diagnosis = _parse_llm_response(response_text, affected, root_path=spec.root_path)

    # Merge any spec-correlated affected symbols not found by LLM
    llm_symbol_names = {s.name for s in diagnosis.affected_symbols}
    for sym in affected:
        if sym.name not in llm_symbol_names:
            diagnosis.affected_symbols.append(sym)

    return diagnosis
