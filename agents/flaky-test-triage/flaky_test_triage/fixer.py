"""Auto-fix suggestions as unified diffs.

Deterministic, rule-based rewrites for the most common flaky-test causes.
This tool NEVER writes to disk. It only returns a diff for a human to review.
"""
from __future__ import annotations

import difflib
import re

from .batch import PROJECT_ROOT, safe_path
from .guardrails import redact_secrets

ALLOWED_SUFFIXES = {".java", ".py", ".kt", ".js", ".ts"}
MAX_SOURCE_BYTES = 100_000

CATEGORY_RULES = {
    "timing_synchronization": ["sleep_to_wait"],
    "locator_ui_change": ["brittle_xpath"],
    "test_data_state": ["static_email"],
}
ALL_RULES = ["sleep_to_wait", "brittle_xpath", "static_email"]

_SLEEP = re.compile(r"^(\s*)Thread\.sleep\(\s*\d+L?\s*\)\s*;\s*$")
_FIND = re.compile(r"driver\.findElement\((By\.\w+\((?:\"[^\"]*\"|'[^']*')\))\)\.(\w+)\(")
_METHOD = re.compile(
    r"^\s*(?:public|private|protected)?\s*(?:static\s+)?[\w<>\[\],.? ]+\s+(\w+)\s*\([^)]*\)\s*(?:throws [\w, .]+)?\s*\{\s*$")
_KEYWORDS = {"if", "for", "while", "switch", "catch", "synchronized"}
_XPATH = re.compile(r'By\.xpath\("(/[^"]*\[\d+\][^"]*)"\)')
_EMAIL = re.compile(r'(?P<q>["\'])(?P<local>[\w.+-]+)@(?P<dom>[\w-]+(?:\.[\w-]+)+)(?P=q)')


def _add_java_imports(lines: list[str], needed: list[str]) -> list[str]:
    missing = [i for i in needed if not any(l.strip() == f"import {i};" for l in lines)]
    if not missing:
        return lines
    idx = max((n for n, l in enumerate(lines) if l.startswith("import ")), default=None)
    if idx is None:
        idx = next((n for n, l in enumerate(lines) if l.startswith("package ")), -1)
        new = [""] + [f"import {i};" for i in missing]
    else:
        new = [f"import {i};" for i in missing]
    return lines[: idx + 1] + new + lines[idx + 1:]


def _sleep_to_wait(lines: list[str]) -> tuple[list[str], list[str], list[str]]:
    out, notes, applied = [], [], []
    wait_declared_in_file = any(re.search(r"WebDriverWait\s+wait\b", l) for l in lines)
    i = 0
    while i < len(lines):
        m = _SLEEP.match(lines[i])
        if m:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            f = _FIND.search(lines[j]) if j < len(lines) else None
            if f:
                by, action = f.group(1), f.group(2)
                cond = "elementToBeClickable" if action == "click" else "visibilityOfElementLocated"
                new = lines[j][:f.start()] + f"wait.until(ExpectedConditions.{cond}({by})).{action}(" + lines[j][f.end():]
                if not wait_declared_in_file:
                    for k in range(len(out) - 1, -1, -1):
                        hm = _METHOD.match(out[k])
                        if hm and hm.group(1) not in _KEYWORDS:
                            if not any("WebDriverWait wait" in l for l in out[k + 1:]):
                                out.insert(k + 1, f"{m.group(1)}WebDriverWait wait = new WebDriverWait(driver, Duration.ofSeconds(10));")
                            break
                out.append(new)
                applied.append("sleep_to_wait")
                i = j + 1
                continue
            notes.append(f"line {i + 1}: Thread.sleep is not followed by a findElement call. Replace it with an explicit wait on the condition you need.")
        out.append(lines[i])
        i += 1
    if applied:
        out = _add_java_imports(out, ["java.time.Duration", "org.openqa.selenium.support.ui.ExpectedConditions",
                                      "org.openqa.selenium.support.ui.WebDriverWait"])
    return out, applied, notes


def _brittle_xpath(lines: list[str]) -> tuple[list[str], list[str], list[str]]:
    out, applied = [], []
    for line in lines:
        m = _XPATH.search(line)
        if m and not line.lstrip().startswith("//"):
            indent = re.match(r"\s*", line).group(0)
            out.append(f"{indent}// FIXME: positional XPath {m.group(1)} is brittle. Confirm the real data-testid with the dev team.")
            out.append(line.replace(m.group(0), "By.cssSelector(\"[data-testid='TODO-confirm-with-dev']\")"))
            applied.append("brittle_xpath")
        else:
            out.append(line)
    return out, applied, []


def _static_email(lines: list[str]) -> tuple[list[str], list[str], list[str]]:
    out, applied = [], []
    for line in lines:
        if line.lstrip().startswith("#") or "uuid" in line:
            out.append(line)
            continue
        new = _EMAIL.sub(lambda m: f"f{m['q']}{{uuid.uuid4().hex[:8]}}-{m['local']}@{m['dom']}{m['q']}", line)
        if new != line:
            applied.append("static_email")
        out.append(new)
    if applied and not any(l.strip() == "import uuid" for l in out):
        idx = max((n for n, l in enumerate(out[:40]) if re.match(r"(import|from) \w", l)), default=None)
        out.insert(0 if idx is None else idx + 1, "import uuid")
    return out, applied, []


def fix_source(text: str, filename: str, rules: list[str]) -> tuple[str, list[str], list[str]]:
    """Apply rules to source text. Returns (new_text, applied_rules, notes)."""
    lines = text.split("\n")
    applied_all, notes_all = [], []
    is_java = filename.endswith((".java", ".kt"))
    is_py = filename.endswith(".py")
    for rule in rules:
        if rule == "sleep_to_wait" and is_java:
            lines, a, n = _sleep_to_wait(lines)
        elif rule == "brittle_xpath":
            lines, a, n = _brittle_xpath(lines)
        elif rule == "static_email" and is_py:
            lines, a, n = _static_email(lines)
        else:
            continue
        applied_all += a
        notes_all += n
    return "\n".join(lines), applied_all, notes_all


def suggest_fix_diff(source_path: str, category: str = "") -> dict:
    """Suggest a patch (unified diff) that fixes a flaky or broken test file.

    Reads a test source file inside the project and returns a diff. It never
    modifies the file.

    Args:
        source_path: Path of a test source file inside the project,
            for example "sample_src/CheckoutTest.java".
        category: Optional failure category from the triage result:
            timing_synchronization, locator_ui_change or test_data_state.
            Leave empty to try every rule.

    Returns:
        A dict with changed (bool), rules_applied, diff, notes and a reminder
        that the patch is only a suggestion.
    """
    try:
        p = safe_path(source_path, must_be_dir=False)
    except ValueError as e:
        return {"error": str(e)}
    if p.suffix.lower() not in ALLOWED_SUFFIXES:
        return {"error": f"unsupported file type, allowed: {sorted(ALLOWED_SUFFIXES)}"}
    if p.stat().st_size > MAX_SOURCE_BYTES:
        return {"error": "source file too large"}
    if category and category not in CATEGORY_RULES:
        return {"changed": False, "rules_applied": [], "diff": "",
                "notes": [f"'{category}' problems are not fixable by editing test code. "
                          "Check the environment or the product behaviour instead."]}
    rules = CATEGORY_RULES.get(category, ALL_RULES)
    old = p.read_text(encoding="utf-8", errors="replace")
    new, applied, notes = fix_source(old, p.name, rules)
    rel = p.relative_to(PROJECT_ROOT).as_posix()
    diff = "\n".join(difflib.unified_diff(old.split("\n"), new.split("\n"),
                                          fromfile=f"a/{rel}", tofile=f"b/{rel}", lineterm=""))
    diff, _ = redact_secrets(diff, skip=("EMAIL",))
    if not applied and not notes:
        notes.append("No automatic fix rule matched. Review the failure manually.")
    return {"changed": bool(applied), "rules_applied": sorted(set(applied)), "diff": diff,
            "notes": notes, "reminder": "Suggested patch only. It was NOT applied. Review and test before merging."}
