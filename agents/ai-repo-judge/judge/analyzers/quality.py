"""Code quality: tests, complexity, typing, docs, error handling, structure and lint.

Python gets deep AST metrics plus ruff; other languages get lighter heuristics.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

from judge.analyzers import pyast
from judge.models import AnalyzerResult, Check, Finding
from judge.workspace import Workspace

DIM = "quality"
RUFF_RULES = "E9,F,B,UP,SIM,PL,RET,ERA"


def _band(value: float, good: float, ok: float, higher_is_better: bool = True) -> str:
    if higher_is_better:
        return "pass" if value >= good else "warn" if value >= ok else "fail"
    return "pass" if value <= good else "warn" if value <= ok else "fail"


def analyze(ws: Workspace, *, run_ruff: bool = True) -> AnalyzerResult:
    r = AnalyzerResult()
    src_loc = sum(ws.line_count(f) for f in ws.source_files)
    test_loc = sum(ws.line_count(f) for f in ws.test_files)

    # Q1 tests
    test_fns = 0
    for f in ws.test_files:
        tree = ws.ast(f)
        if tree is not None:
            test_fns += sum(1 for fn in pyast.functions(tree) if fn.name.startswith("test"))
        else:
            test_fns += len(re.findall(r"\b(?:it|test)\s*\(", ws.read(f) or ""))
    ratio = test_loc / src_loc if src_loc else 0.0
    if not ws.source_files:
        st, score = "skip", None
    elif not ws.test_files or test_fns == 0:
        st, score = "fail", 0.0
    else:
        score = min(1.0, 0.5 + ratio * 2.5)
        st = "pass" if ratio >= 0.15 and test_fns >= 3 else "warn"
    r.checks.append(
        Check(
            id="tests",
            dimension=DIM,
            label="Automated tests exist and cover the code",
            weight=3,
            status=st,
            score=score,
            detail=f"{len(ws.test_files)} test file(s), {test_fns} test(s), test/source LOC {ratio:.2f}"
            if ws.test_files
            else "No tests found",
            fix=f"Add {_test_tool(ws)} tests for the core logic; stub the model so they run without API keys."
            if st != "pass"
            else None,
        )
    )

    # Python AST metrics
    fns: list[tuple[str, ast.AST, int, int]] = []  # (file, node, length, complexity)
    annotated = annotatable = documented = documentable = 0
    swallowed: list[tuple[str, int]] = []
    prints = 0
    uses_logging = False
    for rel in ws.py_files:
        tree = ws.ast(rel)
        if tree is None or ws.is_test_file(rel):
            continue
        documentable += 1
        documented += ast.get_docstring(tree) is not None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                length = (node.end_lineno or node.lineno) - node.lineno + 1
                fns.append((rel, node, length, pyast.complexity(node)))
                args = [a for a in node.args.args + node.args.kwonlyargs if a.arg not in ("self", "cls")]
                annotatable += len(args) + 1
                annotated += sum(a.annotation is not None for a in args) + (node.returns is not None)
                if not node.name.startswith("_") or length > 15:
                    documentable += 1
                    documented += ast.get_docstring(node) is not None
            elif isinstance(node, ast.ClassDef):
                documentable += 1
                documented += ast.get_docstring(node) is not None
            elif isinstance(node, ast.ExceptHandler):
                bare = node.type is None
                silent = all(
                    isinstance(s, (ast.Pass, ast.Continue))
                    or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
                    for s in node.body
                )
                if bare or silent:
                    swallowed.append((rel, node.lineno))
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                prints += 1
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                uses_logging |= any(m in ("logging", "loguru", "structlog") for m in mods)

    if fns:
        # Judge the distribution, not the single worst function: one gnarly parser shouldn't sink a codebase.
        worst = max(fns, key=lambda x: x[3])
        max_cx = worst[3]
        complex_share = sum(1 for x in fns if x[3] > 10) / len(fns)
        cx_score = max(0.0, min(1.0, 1 - complex_share * 3 - max(0, max_cx - 25) / 50))
        st = (
            "pass"
            if complex_share <= 0.05 and max_cx <= 15
            else "warn"
            if complex_share <= 0.15 and max_cx <= 30
            else "fail"
        )
        r.checks.append(
            Check(
                id="complexity",
                dimension=DIM,
                label="Functions stay simple (cyclomatic complexity ≤ 10)",
                weight=2,
                status=st,
                score=cx_score,
                detail=f"{complex_share:.0%} of {len(fns)} functions over 10; max {max_cx} in "
                f"`{getattr(worst[1], 'name', '?')}` ({worst[0]})",
                fix="Split complex functions into smaller helpers." if st != "pass" else None,
            )
        )
        long_fns = [x for x in fns if x[2] > 60]
        long_share = len(long_fns) / len(fns)
        r.checks.append(
            Check(
                id="function_length",
                dimension=DIM,
                label="Functions are short (≤ 60 lines)",
                weight=1,
                status="pass" if long_share <= 0.05 else "warn" if long_share <= 0.15 else "fail",
                score=max(0.0, 1 - long_share * 4),
                detail=f"{len(long_fns)} of {len(fns)} functions over 60 lines"
                + (
                    ": " + ", ".join(f"{getattr(n, 'name', '?')} ({ln})" for _, n, ln, _ in long_fns[:4])
                    if long_fns
                    else ""
                ),
            )
        )
        for rel, node, _, cx in sorted(fns, key=lambda x: -x[3])[:3]:
            if cx > 12:
                r.findings.append(
                    Finding(
                        dimension=DIM,
                        severity="low",
                        file=rel,
                        line=node.lineno,
                        title=f"High complexity ({cx}) in {getattr(node, 'name', '?')}",
                        fix="Extract branches into named helper functions.",
                    )
                )
    if annotatable:
        hint = annotated / annotatable
        r.checks.append(
            Check(
                id="type_hints",
                dimension=DIM,
                label="Type hints on function signatures",
                weight=1,
                status=_band(hint, 0.6, 0.25),
                score=min(1.0, hint / 0.8),
                detail=f"{hint:.0%} of parameters/returns annotated",
            )
        )
    if documentable:
        doc = documented / documentable
        r.checks.append(
            Check(
                id="docstrings",
                dimension=DIM,
                label="Modules, classes and public functions documented",
                weight=1,
                status=_band(doc, 0.5, 0.2),
                score=min(1.0, doc / 0.7),
                detail=f"{doc:.0%} have docstrings",
            )
        )
    if ws.py_files:
        n = len(swallowed)
        r.checks.append(
            Check(
                id="error_handling",
                dimension=DIM,
                label="No bare or silently swallowed exceptions",
                weight=2,
                status="pass" if n == 0 else "warn" if n <= 2 else "fail",
                score=max(0.0, 1 - 0.25 * n),
                detail=f"{n} swallowed/bare except block(s)",
                fix="Catch specific exceptions and log or surface them." if n else None,
            )
        )
        for rel, line in swallowed[:5]:
            r.findings.append(
                Finding(
                    dimension=DIM,
                    severity="low",
                    file=rel,
                    line=line,
                    title="Exception swallowed",
                    snippet=pyast.segment(ws.read(rel) or "", line, 1),
                    fix="Catch a specific exception and log it.",
                )
            )
        per_100 = prints / max(1, src_loc) * 100
        st = "pass" if uses_logging or per_100 <= 3 else "warn"
        r.checks.append(
            Check(
                id="logging",
                dimension=DIM,
                label="Uses logging rather than scattered print()",
                weight=1,
                status=st,
                detail=f"logging {'used' if uses_logging else 'not used'}; {prints} print() calls",
            )
        )

    # Q modularity
    if ws.source_files:
        sizes = sorted(((ws.line_count(f), f) for f in ws.source_files), reverse=True)
        biggest, name = sizes[0]
        single = len(ws.source_files) == 1 and biggest > 250
        st = "fail" if biggest > 700 else "warn" if biggest > 400 or single else "pass"
        r.checks.append(
            Check(
                id="modularity",
                dimension=DIM,
                label="Code split into focused modules",
                weight=1,
                status=st,
                detail=f"{len(ws.source_files)} source file(s); largest {name} ({biggest} lines)",
                fix="Separate CLI, core logic, LLM client and tools into modules." if st != "pass" else None,
            )
        )

    # Q lint
    lint = _ruff(ws) if run_ruff and ws.py_files else None
    if lint is not None:
        issues, by_code = lint
        per_100 = len(issues) / max(1, src_loc + test_loc) * 100
        r.checks.append(
            Check(
                id="lint",
                dimension=DIM,
                label="Lint clean (ruff: pyflakes, bugbear, pylint subset)",
                weight=2,
                status=_band(per_100, 2, 6, higher_is_better=False),
                score=max(0.0, 1 - per_100 / 12),
                detail=f"{len(issues)} issue(s), {per_100:.1f} per 100 lines"
                + (": " + ", ".join(f"{c}×{n}" for c, n in by_code[:5]) if by_code else ""),
            )
        )
        for item in issues[:6]:
            if item["code"].startswith(("F", "B", "E9")):
                r.findings.append(
                    Finding(
                        dimension=DIM,
                        severity="low",
                        file=item["file"],
                        line=item["line"],
                        title=f"ruff {item['code']}: {item['message']}"[:120],
                    )
                )
    elif ws.js_files and not ws.py_files:
        js_loc = sum(ws.line_count(f) for f in ws.js_files)
        logs = sum(len(re.findall(r"console\.log\(", ws.read(f) or "")) for f in ws.js_files)
        anys = sum(len(re.findall(r":\s*any\b", ws.read(f) or "")) for f in ws.js_files if f.endswith((".ts", ".tsx")))
        per_100 = (logs + anys) / max(1, js_loc) * 100
        r.checks.append(
            Check(
                id="lint",
                dimension=DIM,
                label="JS/TS hygiene (console.log, `any`)",
                weight=2,
                status=_band(per_100, 1, 4, higher_is_better=False),
                score=max(0.0, 1 - per_100 / 8),
                detail=f"{logs} console.log, {anys} `any` in {js_loc} lines",
            )
        )

    r.facts.update(
        loc_source=src_loc, loc_tests=test_loc, functions=len(fns), max_complexity=max((x[3] for x in fns), default=0)
    )
    return r


def _test_tool(ws: Workspace) -> str:
    langs = {ws.language(f) for f in ws.source_files}
    if "Python" in langs:
        return "pytest"
    if "Go" in langs:
        return "`go test`"
    if langs & {"JavaScript", "TypeScript"}:
        return "Vitest/Jest"
    return "automated"


def _ruff(ws: Workspace) -> tuple[list[dict], list[tuple[str, int]]] | None:
    """Run ruff (a pure parser; it never executes the code) with fixed rules for a fair comparison."""
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "ruff",
                "check",
                "--isolated",
                "--no-cache",
                "--exit-zero",
                "--quiet",
                "--output-format",
                "json",
                "--select",
                RUFF_RULES,
                "--ignore",
                "PLR2004,PLR0913,PLC0415,PLW0603",
                "--line-length",
                "120",
                *[str(ws.path(f)) for f in ws.py_files[:500]],
            ],
            cwd=ws.root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        raw = json.loads(proc.stdout or "[]")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None
    issues = [
        {
            "code": i.get("code") or "E",
            "message": i.get("message", ""),
            "line": i["location"]["row"],
            "file": _rel(ws, i.get("filename", "")),
        }
        for i in raw
    ]
    counts: dict[str, int] = {}
    for i in issues:
        counts[i["code"]] = counts.get(i["code"], 0) + 1
    return issues, sorted(counts.items(), key=lambda kv: -kv[1])


def _rel(ws: Workspace, path: str) -> str:
    p = Path(path).resolve()
    if p.is_relative_to(ws.root.resolve()):
        return p.relative_to(ws.root.resolve()).as_posix()
    if ws.repo_root is not None and p.is_relative_to(ws.repo_root.resolve()):
        return "/" + p.relative_to(ws.repo_root.resolve()).as_posix()
    return path
