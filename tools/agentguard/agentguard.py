#!/usr/bin/env python3
"""AgentGuard: lightweight static checks for AI-agent project reliability."""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    path: str
    line: int
    message: str
    recommendation: str


SECRET_PATTERNS = [
    ("AG001", re.compile(r"(?i)\b(?:OPENAI|ANTHROPIC|GOOGLE|GEMINI|AWS|GITHUB)_?(?:API_?)?(?:KEY|TOKEN|SECRET)\s*=\s*['\"](?!your_|replace_|example|xxx)[A-Za-z0-9_\-/+=]{12,}['\"]"), "Possible hardcoded credential", "Read credentials from environment variables or a secret manager; rotate exposed keys."),
    ("AG002", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "Possible provider API key in source", "Remove the key from source history and rotate it immediately."),
]


def _python_findings(path: Path, text: str, rel: str) -> list[Finding]:
    findings: list[Finding] = []
    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError as exc:
        return [Finding("AG000", "INFO", rel, exc.lineno or 1, "Python file could not be parsed; AST checks were skipped.", "Fix the syntax error to enable structural checks.")]

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = ""
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if name in {"requests", "get", "post", "put", "delete", "request"}:
                # Avoid falsely treating arbitrary .get() calls as network calls; only flag requests.*.
                is_requests_call = isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "requests"
                if is_requests_call and not any(k.arg == "timeout" for k in node.keywords):
                    findings.append(Finding("AG101", "MEDIUM", rel, node.lineno, "HTTP request has no explicit timeout.", "Set a finite timeout (for example, timeout=10) so a stalled service cannot hang the agent."))
            if name in {"eval", "exec"}:
                findings.append(Finding("AG201", "HIGH", rel, node.lineno, f"Dynamic code execution via {name}().", "Avoid executing model-generated or untrusted strings; use an explicit allowlisted tool interface."))
        if isinstance(node, ast.While) and isinstance(node.test, ast.Constant) and node.test.value is True:
            # A while-true loop can be legitimate, so make the finding advisory.
            findings.append(Finding("AG102", "LOW", rel, node.lineno, "Unconditional while True loop may run indefinitely.", "Ensure the loop has a clear stop condition, iteration budget, cancellation path, or timeout."))
        if isinstance(node, ast.FunctionDef) and any(word in node.name.lower() for word in ("agent", "tool", "run", "execute")):
            if not ast.get_docstring(node):
                findings.append(Finding("AG301", "LOW", rel, node.lineno, f"Function '{node.name}' has no docstring.", "Document expected inputs, side effects, failure modes, and whether the function can access external systems."))
    return findings


def scan_path(root: Path) -> list[Finding]:
    root = root.resolve()
    findings: list[Finding] = []
    skip_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__", ".tox", "dist", "build"}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in skip_dirs for part in path.relative_to(root).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        for rule, pattern, message, recommendation in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(Finding(rule, "HIGH", rel, line, message, recommendation))
        if path.suffix == ".py":
            findings.extend(_python_findings(path, text, rel))
    # Deduplicate identical reports and produce stable output.
    unique = {(f.rule, f.path, f.line, f.message): f for f in findings}
    return sorted(unique.values(), key=lambda f: (f.path, f.line, f.rule))


def render_text(findings: Iterable[Finding], root: Path) -> str:
    items = list(findings)
    counts = {level: sum(f.severity == level for f in items) for level in ("HIGH", "MEDIUM", "LOW", "INFO")}
    lines = [f"AgentGuard report — {root}", f"Findings: {len(items)} | HIGH {counts['HIGH']} · MEDIUM {counts['MEDIUM']} · LOW {counts['LOW']} · INFO {counts['INFO']}", ""]
    if not items:
        lines.append("No findings from the current rule set. This is not a guarantee that the project is secure.")
    for f in items:
        lines.extend([f"[{f.severity}] {f.rule} {f.path}:{f.line} — {f.message}", f"  Fix: {f.recommendation}"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Static checks for common AI-agent reliability and security footguns.")
    parser.add_argument("path", nargs="?", default=".", help="project directory to scan (default: current directory)")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="output format")
    parser.add_argument("--fail-on", choices=("never", "low", "medium", "high"), default="never", help="exit non-zero when a finding at this severity or higher exists")
    args = parser.parse_args(argv)
    root = Path(args.path)
    if not root.exists() or not root.is_dir():
        parser.error(f"path is not a directory: {root}")
    findings = scan_path(root)
    if args.format == "json":
        print(json.dumps({"root": str(root.resolve()), "finding_count": len(findings), "findings": [asdict(f) for f in findings]}, indent=2))
    else:
        print(render_text(findings, root.resolve()))
    rank = {"never": 99, "low": 3, "medium": 2, "high": 1}
    severity_rank = {"HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    threshold = rank[args.fail_on]
    return 1 if args.fail_on != "never" and any(severity_rank[f.severity] <= threshold for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
