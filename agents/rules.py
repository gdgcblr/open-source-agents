"""Deterministic rule catalogue. Fast, free, and explainable: the first line of defence
before the LLM looks at the code."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    id: str
    pattern: re.Pattern
    severity: str
    category: str
    title: str
    detail: str
    suggestion: str
    exclude: re.Pattern | None = None  # skip the match if the line also matches this
    extensions: tuple[str, ...] | None = None  # None = every file type


def _r(p: str, flags: int = 0) -> re.Pattern:
    return re.compile(p, flags)


SECURITY_RULES: list[Rule] = [
    Rule(
        "SEC001", _r(r"AKIA[0-9A-Z]{16}"), "critical", "security",
        "AWS access key committed",
        "A string shaped like an AWS access key ID was added to the codebase.",
        "Remove it, rotate the key immediately, and load credentials from the environment or a secrets manager.",
    ),
    Rule(
        "SEC002", _r(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"), "critical", "security",
        "Private key committed",
        "A PEM private key header was added to the codebase.",
        "Remove the key from history, rotate it, and store it in a secrets manager.",
    ),
    Rule(
        "SEC003",
        _r(r"""(?i)(api[_-]?key|secret|passwd|password|token|client[_-]?secret)\s*[:=]\s*["'][^"'\s]{8,}["']"""),
        "high", "security",
        "Hardcoded credential",
        "A secret-looking value is assigned to a literal string.",
        "Read it from an environment variable or secrets manager; commit only a placeholder in .env.example.",
        exclude=_r(r"(?i)(your|example|changeme|placeholder|dummy|xxx|<.+>|\$\{|os\.environ|getenv)"),
    ),
    Rule(
        "SEC010", _r(r"\b(eval|exec)\s*\("), "high", "security",
        "Dynamic code execution",
        "eval/exec on dynamic input allows arbitrary code execution.",
        "Use ast.literal_eval, a parser, or an explicit dispatch table instead.",
        extensions=("py", "js", "ts", "jsx", "tsx", "php", "rb"),
    ),
    Rule(
        "SEC011", _r(r"subprocess\.\w+\(.*shell\s*=\s*True|\bos\.system\s*\("), "high", "security",
        "Shell command execution",
        "Running commands through a shell exposes the app to command injection.",
        "Pass an argument list with shell=False and validate every user-controlled value.",
        extensions=("py",),
    ),
    Rule(
        "SEC012",
        _r(r"""(?i)(execute|executemany|raw|query)\s*\(\s*(f["']|["'][^"']*["']\s*(%|\+|\.format))"""),
        "high", "security",
        "Possible SQL injection",
        "A SQL statement appears to be built with string formatting or concatenation.",
        "Use parameterised queries (placeholders) so the driver escapes values.",
    ),
    Rule(
        "SEC013", _r(r"\bpickle\.loads?\(|\byaml\.load\((?!.*Loader\s*=\s*(?:yaml\.)?SafeLoader)"), "high", "security",
        "Unsafe deserialisation",
        "pickle / yaml.load on untrusted data can execute arbitrary code.",
        "Use json, or yaml.safe_load.",
        extensions=("py",),
    ),
    Rule(
        "SEC014", _r(r"verify\s*=\s*False|rejectUnauthorized\s*:\s*false"), "high", "security",
        "TLS verification disabled",
        "Disabling certificate verification enables man-in-the-middle attacks.",
        "Keep verification on; trust a custom CA bundle if needed.",
    ),
    Rule(
        "SEC015", _r(r"(?i)\b(md5|sha1)\s*\("), "medium", "security",
        "Weak hash function",
        "MD5/SHA-1 are broken for security purposes.",
        "Use SHA-256+ (or bcrypt/argon2 for passwords).",
    ),
    Rule(
        "SEC016", _r(r"\bdebug\s*=\s*True\b|\bDEBUG\s*=\s*True\b"), "medium", "security",
        "Debug mode enabled",
        "Debug mode can leak stack traces and enable remote consoles in production.",
        "Drive this from configuration and default to False.",
    ),
    Rule(
        "SEC017", _r(r"\.innerHTML\s*=|dangerouslySetInnerHTML"), "medium", "security",
        "Potential XSS sink",
        "Writing unsanitised HTML into the DOM can enable cross-site scripting.",
        "Use textContent or sanitise with a vetted library (e.g. DOMPurify).",
        extensions=("js", "jsx", "ts", "tsx", "html"),
    ),
]

QUALITY_RULES: list[Rule] = [
    Rule(
        "QUA001", _r(r"^\s*except\s*:\s*(#.*)?$"), "medium", "quality",
        "Bare except",
        "A bare `except:` swallows every error, including KeyboardInterrupt.",
        "Catch the specific exception types you expect.",
        extensions=("py",),
    ),
    Rule(
        "QUA002", _r(r"\b(TODO|FIXME|HACK|XXX)\b"), "low", "quality",
        "Unresolved TODO/FIXME",
        "A TODO marker is being merged.",
        "Resolve it or link it to a tracked issue.",
    ),
    Rule(
        "QUA003", _r(r"^\s*print\("), "low", "quality",
        "Debug print left in code",
        "print() statements usually are not meant to ship.",
        "Use the logging module.",
        extensions=("py",),
    ),
    Rule(
        "QUA004", _r(r"\bconsole\.log\("), "low", "quality",
        "console.log left in code",
        "Console logging usually is not meant to ship.",
        "Remove it or use a proper logger.",
        extensions=("js", "jsx", "ts", "tsx"),
    ),
    Rule(
        "QUA005", _r(r"def\s+\w+\(.*=\s*(\[\]|\{\}|set\(\))\s*[,)]"), "medium", "bug",
        "Mutable default argument",
        "Default list/dict/set objects are shared between calls.",
        "Default to None and create the object inside the function.",
        extensions=("py",),
    ),
    Rule(
        "QUA006", _r(r"[=!]=\s*None\b"), "low", "style",
        "Compare to None with `is`",
        "Equality against None can be overridden by __eq__.",
        "Use `is None` / `is not None`.",
        extensions=("py",),
    ),
]

SOURCE_EXTENSIONS = {"py", "js", "jsx", "ts", "tsx", "go", "rs", "java", "rb", "php", "cs", "kt"}
MAX_LINE_LENGTH = 120
LARGE_FILE_ADDED_LINES = 400
