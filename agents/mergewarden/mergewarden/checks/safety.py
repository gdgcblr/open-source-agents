"""Cross-check risky capabilities in code against what the README discloses,
and flag install hooks that run code on `npm install` / `pip install`."""

from __future__ import annotations

import json
import re

from ..models import Criterion, Finding, Severity, Submission
from ..policy import Policy
from ._files import is_test_file, read
from .readme import _find_section, sections

RISKY = {
    "runs shell commands": r"\bsubprocess\b|os\.(?:system|popen|exec\w*|spawn\w*)\(|\bpty\.|child_process|"
                           r"exec\.Command\(|\bshell=True|\bcommands\.getoutput",
    "evaluates dynamic code": r"(?<![\w.])(?:eval|exec|compile)\(|__import__\(|importlib\.import_module\(",
}
DISCLOSED = re.compile(r"(?i)sandbox|confirm|approval|allow-?list|docker|container|human[- ]in[- ]the[- ]loop|read-only|timeout")
NEGATED = re.compile(r"(?i)\b(?:no|not|without|never|lacks?|isn't|doesn't|don't|n't)\b[\w\s,/-]{0,25}$")
HOOKS = ("preinstall", "install", "postinstall", "prepare", "prepublish", "preprepare")
CODE_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rs", ".sh", ".rb"}


def disclosed(text: str) -> bool:
    """A sandbox/timeout/confirmation is mentioned, and not as "no sandbox"."""
    return any(not NEGATED.search(text[max(0, m.start() - 40): m.start()]) for m in DISCLOSED.finditer(text))


def check(sub: Submission, policy: Policy) -> list[Finding]:
    if not sub.project_dir:
        return []
    out: list[Finding] = []
    found: dict[str, str] = {}
    for f in sub.project_files():
        rel = str(f.relative_to(sub.root))
        if f.name == "package.json":
            out += _npm_hooks(f, rel)
        if f.name == "setup.py" and "cmdclass" in read(f):
            out.append(Finding(
                "safety.install-hook", Severity.MAJOR, Criterion.SECURITY,
                f"`{rel}` overrides setup commands (`cmdclass`), so arbitrary code runs on `pip install`.",
                file=rel, fix="Remove the custom cmdclass, or explain exactly what it runs in the README's Security section.",
                rule=policy.rule("safety.loops"),
            ))
        if f.suffix not in CODE_EXT or is_test_file(rel):
            continue
        text = read(f)
        for what, pat in RISKY.items():
            if what not in found and re.search(pat, text):
                found[what] = rel
    if found:
        sec = _find_section(sections(sub.read("README.md")), "Security & Privacy Considerations") or ""
        if not disclosed(sec):
            out += [Finding(
                "safety.undisclosed-execution", Severity.MAJOR, Criterion.SECURITY,
                f"Code {what} (`{where}`) but the README's Security section doesn't explain the sandboxing, "
                "timeout or user confirmation around it.",
                file=where, fix="Describe in 'Security & Privacy Considerations' what is executed and how it is contained.",
                rule=policy.rule("safety.loops"),
            ) for what, where in found.items()]
    return out


def _npm_hooks(f, rel: str) -> list[Finding]:
    try:
        scripts = json.loads(read(f)).get("scripts") or {}
    except (ValueError, AttributeError):
        return []
    hooks = {k: v for k, v in scripts.items() if k in HOOKS}
    if not hooks:
        return []
    shown = ", ".join(f"`{k}: {str(v)[:60]}`" for k, v in hooks.items())
    return [Finding(
        "safety.install-hook", Severity.MAJOR, Criterion.SECURITY,
        f"`{rel}` has install-time scripts that run automatically on `npm install`: {shown}.",
        file=rel, fix="Remove install hooks, or make them explicit commands documented in the README.",
    )]
