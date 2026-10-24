"""Cross-check risky capabilities in code against what the README discloses."""

from __future__ import annotations

import re

from ..models import Criterion, Finding, Severity, Submission
from ..policy import Policy
from .readme import _find_section, sections

RISKY = {
    "runs shell commands": r"\bsubprocess\.|os\.system\(|child_process|exec\.Command\(|\bshell=True",
    "evaluates dynamic code": r"(?<![\w.])(?:eval|exec)\(",
}
DISCLOSED = re.compile(r"(?i)sandbox|confirm|approval|allow-?list|docker|container|human[- ]in[- ]the[- ]loop|read-only|timeout")


def check(sub: Submission, policy: Policy) -> list[Finding]:
    if not sub.project_dir:
        return []
    found: dict[str, str] = {}
    for f in sub.project_files():
        if f.suffix not in {".py", ".js", ".ts", ".go"} or "test" in f.name:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for what, pat in RISKY.items():
            if what not in found and re.search(pat, text):
                found[what] = str(f.relative_to(sub.root))
    if not found:
        return []
    sec = _find_section(sections(sub.read("README.md")), "Security & Privacy Considerations") or ""
    if DISCLOSED.search(sec):
        return []
    return [Finding(
        "safety.undisclosed-execution", Severity.MINOR, Criterion.SECURITY,
        f"Code {what} (`{where}`) but the README's Security section doesn't explain sandboxing or user confirmation.",
        file=where, fix="Describe in 'Security & Privacy Considerations' what is executed and how it is contained.",
        rule=policy.rule("safety.loops"),
    ) for what, where in found.items()]
