"""Checks for agent safety heuristics: execution loops, hidden Unicode, and capabilities disclosure (A01, A02, A03)."""

from __future__ import annotations

import ast
import re
from typing import Any

from merge_ready.model import Finding, RuleResult, Severity, Verdict
from merge_ready.project import ProjectContext

# Unicode ranges & sets
BIDI_CHARS = set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A))
TAG_CHARS = set(range(0xE0000, 0xE0080))
ZERO_WIDTH_WARNINGS = {0x200B, 0x2060}  # zero-width space, word joiner

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".bmp", ".tiff",
    ".pdf", ".zip", ".tar", ".gz", ".7z", ".rar",
    ".sqlite", ".sqlite3", ".db", ".db3", ".bin", ".exe", ".dll", ".so", ".dylib",
    ".pyc", ".pyo", ".woff", ".woff2", ".ttf", ".eot",
}

MODEL_CALL_NAMES = {
    "generate_content",
    "send_message",
    "chat",
    "invoke",
    "run_agent",
    "execute_step",
    "step",
    "predict",
    "create_chat_completion",
}

SHELL_CALL_PATTERNS = [
    ("subprocess", "subprocess"),
    ("os.system", "os.system"),
    ("os.popen", "os.popen"),
    ("eval", "eval"),
    ("exec", "exec"),
]

SHELL_DISCLOSURE_KEYWORDS = [
    "shell",
    "subprocess",
    "command execution",
    "sandbox",
    "sandboxing",
    "guardrail",
    "guardrails",
    "eval",
    "arbitrary code",
    "user confirmation",
    "confirmation",
    "allowlist",
    "safeguard",
]


def decode_tag_chars(text: str) -> str:
    """Decode hidden Unicode tag characters into their ASCII payload (ch - 0xE0000)."""
    chars = []
    for ch in text:
        cp = ord(ch)
        if cp in TAG_CHARS:
            ascii_cp = cp - 0xE0000
            if 0x20 <= ascii_cp <= 0x7E:
                chars.append(chr(ascii_cp))
    return "".join(chars)


def scan_unicode(text: str) -> list[tuple[Severity, int, int, int, str]]:
    """Scan text for malicious or deceptive Unicode characters."""
    findings: list[tuple[Severity, int, int, int, str]] = []

    lines = text.splitlines()
    for ln, line in enumerate(lines, 1):
        for col, ch in enumerate(line, 1):
            cp = ord(ch)

            # High severity: Bidi controls and hidden tag characters
            if cp in BIDI_CHARS:
                findings.append(
                    (
                        Severity.ERROR,
                        ln,
                        col,
                        cp,
                        f"Trojan Source bidirectional control character (U+{cp:04X}, CVE-2021-42574) reordering visual display",
                    )
                )
            elif cp in TAG_CHARS:
                findings.append(
                    (
                        Severity.ERROR,
                        ln,
                        col,
                        cp,
                        f"Plane 14 Unicode tag character (U+{cp:05X}) used for invisible prompt injection against LLMs",
                    )
                )
            # Mid-file BOM
            elif cp == 0xFEFF:
                if not (ln == 1 and col == 1):
                    findings.append(
                        (Severity.WARNING, ln, col, cp, f"Mid-file Byte Order Mark (U+FEFF)")
                    )
            # Suspicious zero-width characters (excluding legitimate ZWJ in emojis)
            elif cp in ZERO_WIDTH_WARNINGS:
                findings.append(
                    (Severity.WARNING, ln, col, cp, f"Zero-width invisible character (U+{cp:04X})")
                )
            # ZWJ check (U+200D): flag only if not preceded or followed by emoji/presentation
            elif cp == 0x200D:
                prev_ch = line[col - 2] if col >= 2 else ""
                next_ch = line[col] if col < len(line) else ""
                # If neither adjacent character is in high emoji planes (> 0x2000), warn
                if (not prev_ch or ord(prev_ch) < 0x2000) and (not next_ch or ord(next_ch) < 0x2000):
                    findings.append(
                        (Severity.WARNING, ln, col, cp, f"Isolated zero-width joiner (U+200D)")
                    )

    return findings


def has_loop_exit(nodes: list[ast.stmt]) -> bool:
    """Check if AST block contains an explicit break, return, raise, or guarded condition."""
    for node in nodes:
        if isinstance(node, (ast.Break, ast.Return, ast.Raise)):
            return True
        if isinstance(node, ast.If):
            # Check if condition checks iteration/time or body exits
            if has_loop_exit(node.body) or has_loop_exit(node.orelse):
                return True
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.Break, ast.Return, ast.Raise)):
                return True
    return False


def body_has_model_call(nodes: list[ast.stmt]) -> bool:
    """Check if loop body contains an LLM or agent invocation call."""
    for node in nodes:
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                func = child.func
                func_name = ""
                if isinstance(func, ast.Name):
                    func_name = func.id
                elif isinstance(func, ast.Attribute):
                    func_name = func.attr
                if any(m in func_name.lower() for m in MODEL_CALL_NAMES):
                    return True
    return False


def check_a01(ctx: ProjectContext, config: dict[str, Any]) -> RuleResult:
    """A01: Heuristic check for potentially unbounded execution loops around model calls."""
    rule_id = "A01"
    name = "Unbounded Execution Loops"
    source = config.get("source_rule", "CONTRIBUTING.md Quality & Security Standards (Safety & Respect)")
    findings: list[Finding] = []

    for rel_path in ctx.files:
        if rel_path.suffix != ".py":
            continue
        posix = rel_path.as_posix()
        txt = ctx.read_text(rel_path)
        if not txt:
            continue

        try:
            tree = ast.parse(txt, filename=posix)
            for node in ast.walk(tree):
                # 1. Plain while True / while 1
                if isinstance(node, ast.While):
                    is_infinite_test = False
                    if isinstance(node.test, ast.Constant) and node.test.value in (True, 1):
                        is_infinite_test = True

                    if is_infinite_test:
                        if body_has_model_call(node.body):
                            if not has_loop_exit(node.body):
                                findings.append(
                                    Finding(
                                        rule_id=rule_id,
                                        severity=Severity.WARNING,
                                        message="Potentially unbounded 'while True' loop around model/agent invocation.",
                                        path=posix,
                                        line=node.lineno,
                                        evidence="While loop test is constant True and body calls model without explicit exit condition.",
                                        fix="Add an iteration counter, timeout limit, or explicit break condition to bound execution.",
                                        source_rule=source,
                                    )
                                )

                # 2. ADK LoopAgent instantiation
                elif isinstance(node, ast.Call):
                    func_name = ""
                    if isinstance(node.func, ast.Name):
                        func_name = node.func.id
                    elif isinstance(node.func, ast.Attribute):
                        func_name = node.func.attr

                    if func_name == "LoopAgent":
                        has_max_iter = any(kw.arg == "max_iterations" for kw in node.keywords)
                        if not has_max_iter:
                            findings.append(
                                Finding(
                                    rule_id=rule_id,
                                    severity=Severity.WARNING,
                                    message="LoopAgent instantiated with no explicit 'max_iterations' bound.",
                                    path=posix,
                                    line=node.lineno,
                                    evidence="LoopAgent() called without max_iterations argument.",
                                    fix="Pass 'max_iterations=<int>' to LoopAgent to prevent indefinite execution.",
                                    source_rule=source,
                                )
                            )
        except Exception:
            pass

    verdict = Verdict.WARN if findings else Verdict.PASS
    return RuleResult(rule_id=rule_id, name=name, verdict=verdict, findings=findings)


def check_a02(ctx: ProjectContext, config: dict[str, Any]) -> RuleResult:
    """A02: Detect Trojan Source bidi overrides (CVE-2021-42574) and Plane 14 prompt injection tags."""
    rule_id = "A02"
    name = "Hidden and Deceptive Unicode"
    source = config.get("source_rule", "Agent Safety Standard & Trojan Source Defense")
    findings: list[Finding] = []

    # Scan all text and prompt files, skipping only known binary formats
    for rel_path in ctx.files:
        if rel_path.suffix.lower() in BINARY_EXTENSIONS:
            continue
        posix = rel_path.as_posix()
        txt = ctx.read_text(rel_path)
        if not txt:
            continue

        raw_results = scan_unicode(txt)
        if raw_results:
            decoded_payload = decode_tag_chars(txt)
            for sev, ln, col, cp, desc in raw_results[:5]:  # limit findings per file
                evidence = f"Line {ln}, column {col}: {desc}"
                if decoded_payload and cp in TAG_CHARS:
                    evidence += f" [Decoded tag payload: '{decoded_payload}']"

                findings.append(
                    Finding(
                        rule_id=rule_id,
                        severity=sev,
                        message=f"Suspicious Unicode character detected in '{posix}': {desc}.",
                        path=posix,
                        line=ln,
                        evidence=evidence,
                        fix="Remove hidden or bidirectional control characters from prompt and source files.",
                        source_rule=source,
                    )
                )

    has_errors = any(f.severity == Severity.ERROR for f in findings)
    verdict = Verdict.FAIL if has_errors else (Verdict.WARN if findings else Verdict.PASS)
    return RuleResult(rule_id=rule_id, name=name, verdict=verdict, findings=findings)


def check_a03(ctx: ProjectContext, config: dict[str, Any]) -> RuleResult:
    """A03: Ensure high-impact tool capabilities (subprocess, system commands) are disclosed in README."""
    rule_id = "A03"
    name = "High-Impact Capabilities Disclosure"
    source = config.get("source_rule", "template/README.md Security & Privacy Considerations")

    detected_calls: list[tuple[str, int, str]] = []

    for rel_path in ctx.files:
        if rel_path.suffix != ".py":
            continue
        posix = rel_path.as_posix()
        txt = ctx.read_text(rel_path)
        if not txt:
            continue

        try:
            tree = ast.parse(txt, filename=posix)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    call_name = ""
                    if isinstance(node.func, ast.Name):
                        call_name = node.func.id
                    elif isinstance(node.func, ast.Attribute):
                        val = node.func.value
                        val_id = val.id if isinstance(val, ast.Name) else ""
                        call_name = f"{val_id}.{node.func.attr}" if val_id else node.func.attr

                    for pat_sub, label in SHELL_CALL_PATTERNS:
                        if call_name == pat_sub or call_name.startswith(pat_sub + "."):
                            detected_calls.append((posix, node.lineno, label))
        except Exception:
            pass

    if not detected_calls:
        return RuleResult(
            rule_id=rule_id,
            name=name,
            verdict=Verdict.NA,
            reason="No high-impact shell or code execution calls detected.",
        )

    # Check README Security & Privacy section
    readme = ctx.read_text("README.md") or ""
    readme_lower = readme.lower()

    # Find Security & Privacy Considerations section
    sec_match = re.search(r"##\s*Security & Privacy Considerations(.*?)(?:##|\Z)", readme, re.DOTALL | re.IGNORECASE)
    sec_text = sec_match.group(1).lower() if sec_match else readme_lower

    disclosed = any(kw in sec_text for kw in SHELL_DISCLOSURE_KEYWORDS)
    findings: list[Finding] = []

    if not disclosed:
        primary_path, primary_line, label = detected_calls[0]
        findings.append(
            Finding(
                rule_id=rule_id,
                severity=Severity.WARNING,
                message=f"Project executes high-impact command/code capabilities ('{label}') without disclosure in Security section.",
                path=primary_path,
                line=primary_line,
                evidence=f"Called at {primary_path}:{primary_line}. README.md does not describe sandboxing or confirmation safeguards.",
                fix="Document shell/code execution safeguards under '## Security & Privacy Considerations' in README.md.",
                source_rule=source,
            )
        )

    verdict = Verdict.WARN if findings else Verdict.PASS
    return RuleResult(rule_id=rule_id, name=name, verdict=verdict, findings=findings)
