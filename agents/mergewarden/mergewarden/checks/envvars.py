"""Every environment variable the code reads must be documented, or the
reviewer's fresh-clone run fails with a KeyError."""

from __future__ import annotations

import re

from ..models import Criterion, Finding, Severity, Submission
from ..policy import Policy
from ._files import is_test_file, read

READS = [
    # os.getenv / os.environ.get / os.environ[...], with or without the `os.` prefix
    # (`from os import getenv, environ`).
    r"""(?<![\w.])(?:os\.)?(?:getenv|environ\.get|environ\.setdefault)\(\s*["']([A-Z][A-Z0-9_]+)["']""",
    r"""(?<![\w.])(?:os\.)?environ\[\s*["']([A-Z][A-Z0-9_]+)["']\s*\]""",
    r"""process\.env\.([A-Z][A-Z0-9_]+)""",
    r"""process\.env\[\s*["']([A-Z][A-Z0-9_]+)["']\s*\]""",
    r"""os\.Getenv\(\s*"([A-Z][A-Z0-9_]+)"\)""",
    r"""env::var\(\s*"([A-Z][A-Z0-9_]+)"\)""",
]
CODE_EXT = {".py", ".js", ".ts", ".mjs", ".cjs", ".tsx", ".go", ".rs"}
IGNORE = {"PATH", "HOME", "USER", "PYTHONPATH", "NODE_ENV", "CI", "TERM", "PWD", "SHELL", "TMPDIR", "DEBUG"}


def check(sub: Submission, policy: Policy) -> list[Finding]:
    if not sub.project_dir:
        return []
    used: dict[str, str] = {}
    for f in sub.project_files():
        if f.suffix not in CODE_EXT or is_test_file(str(f.relative_to(sub.root))):
            continue
        try:
            text = read(f)
        except OSError:
            continue
        for pat in READS:
            for m in re.finditer(pat, text):
                used.setdefault(m.group(1), str(f.relative_to(sub.root)))
    documented = sub.read(".env.example") + "\n" + sub.read("README.md")
    out = []
    for var, where in sorted(used.items()):
        if var in IGNORE or re.search(rf"\b{var}\b", documented):
            continue
        out.append(Finding(
            "env.undocumented", Severity.MAJOR, Criterion.REPRODUCIBILITY,
            f"`{var}` is read by the code but documented in neither .env.example nor the README.",
            file=where, fix=f"Add `{var}=` with a placeholder to .env.example and a row to the README config table.",
            rule=policy.rule("env.undocumented"),
        ))
    return out
