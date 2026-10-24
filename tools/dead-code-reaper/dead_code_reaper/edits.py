"""Apply removals to source text.

Removals become edits on the original source: line spans are deleted, import
statements that lose only some of their names are rewritten, and unused
modules are deleted whole. The result is always valid Python, or the edit is
refused (None), so a broken file never reaches the test run.
"""
from __future__ import annotations

import ast
from collections import defaultdict

from .model import Removal


def _import_line(info: dict, keep: list[list]) -> str:
    names = ", ".join(n if not a else f"{n} as {a}" for n, a in keep)
    indent = " " * info["col"]
    if info["is_from"]:
        return f"{indent}from {'.' * info['level']}{info['module'] or ''} import {names}\n"
    return f"{indent}import {names}\n"


def edit_source(source: str, removals: list[Removal]) -> str | None:
    """Return `source` with the removals applied, or None if that can't be done cleanly."""
    if not removals:
        return source
    ops: list[tuple[int, int, int, str | None]] = []  # (start, end, col, replacement or None)

    imports: dict[int, list[Removal]] = defaultdict(list)
    for r in removals:
        if r.kind == "import":
            imports[r.import_info["stmt_start"]].append(r)
        else:
            ops.append((r.start, r.end, r.col, None))
    for stmt_start, items in imports.items():
        info = items[0].import_info
        drop = {r.import_info["drop"] for r in items}
        keep = [a for a in info["aliases"] if a[0] not in drop]
        replacement = None if not keep else _import_line(info, keep)
        ops.append((info["stmt_start"], info["stmt_end"], info["col"], replacement))

    # Drop edits nested inside a larger deletion.
    ops.sort(key=lambda o: (o[0], -o[1]))
    outer: list[tuple[int, int, int, str | None]] = []
    for op in ops:
        if outer and op[0] >= outer[-1][0] and op[1] <= outer[-1][1]:
            if outer[-1][3] is None:
                continue
            return None  # an edit inside a rewritten import: shouldn't happen
        if outer and op[0] <= outer[-1][1]:
            return None  # partial overlap
        outer.append(op)

    lines = source.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"

    def build(with_pass: bool) -> str:
        out = list(lines)
        for start, end, col, replacement in reversed(outer):
            s, e = start, end
            if replacement is not None:
                out[s - 1:e] = [replacement]
                continue
            # Keep the spacing a human would leave: the gap that remains is the
            # larger of the blank runs that were above and below the deleted code.
            before = 0
            while s - 2 - before >= 0 and out[s - 2 - before].strip() == "":
                before += 1
            after = 0
            while e + after < len(out) and out[e + after].strip() == "":
                after += 1
            if e + after >= len(out):          # deleting up to the end of the file
                s, e = s - before, e + after
            elif s == 1:                       # deleting from the top of the file
                e += after
            else:
                e += min(before, after)
            replacement = [" " * col + "pass\n"] if with_pass and col > 0 else []
            out[max(s, 1) - 1:e] = replacement
        return "".join(out)

    for with_pass in (False, True):
        text = build(with_pass)
        try:
            ast.parse(text)
            return text
        except SyntaxError:
            continue
    return None


def apply_removals(sources: dict[str, str], removals: list[Removal]) -> dict[str, str | None] | None:
    """Edit every affected file. Returns {path: new text, or None if the file is deleted}.

    Returns None if any file can't be edited cleanly.
    """
    by_file: dict[str, list[Removal]] = defaultdict(list)
    for r in removals:
        by_file[r.path].append(r)
    result: dict[str, str | None] = {}
    for rel, items in by_file.items():
        if any(r.kind == "module" for r in items):
            result[rel] = None
            continue
        text = edit_source(sources[rel], items)
        if text is None:
            return None
        result[rel] = text
    return result
