"""Apply minimal patches to a prompt and render diffs.

Patches address character offsets in the *original* prompt, so they can be
accepted or rejected independently and applied in one pass.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass

from .schema import Patch


class PatchConflict(ValueError):
    pass


@dataclass
class _Edit:
    pos: int
    end: int
    new: str
    rank: int  # inserts (0) go before a replace (1) starting at the same offset
    order: int
    patch_id: str


def _edits(patches: list[Patch], length: int) -> list[_Edit]:
    out: list[_Edit] = []
    for p in patches:
        if p.op == "wrap":  # prefix at start, suffix at end (the wrapped span itself is untouched)
            out.append(_Edit(p.start, p.start, p.new, 0, -5, p.id))
            out.append(_Edit(p.end, p.end, p.suffix, 0, 1, p.id))
        elif p.op == "insert":
            out.append(_Edit(p.start, p.start, p.new, 0, p.order, p.id))
        elif p.op == "replace":
            out.append(_Edit(p.start, p.end, p.new, 1, p.order, p.id))
        else:
            raise PatchConflict(f"unknown patch op {p.op!r} in {p.id}")
    return out


def check_conflicts(patches: list[Patch], length: int) -> list[tuple[str, str]]:
    """Pairs of patch ids that cannot be applied together."""
    replaces = sorted((p for p in patches if p.op == "replace"), key=lambda p: p.start)
    bad: list[tuple[str, str]] = []
    for a, b in zip(replaces, replaces[1:], strict=False):
        if b.start < a.end:
            bad.append((a.id, b.id))
    for p in patches:
        if p.op in ("insert", "wrap"):
            for r in replaces:
                if r.start < p.start < r.end or (p.op == "wrap" and r.start < p.end < r.end):
                    bad.append((r.id, p.id))
    for p in patches:
        if not (0 <= p.start <= p.end <= length):
            bad.append((p.id, p.id))
    return bad


def apply(text: str, patches: list[Patch]) -> str:
    bad = check_conflicts(patches, len(text))
    if bad:
        raise PatchConflict("conflicting patches: " + ", ".join(f"{a}/{b}" for a, b in bad))
    edits = sorted(_edits(patches, len(text)), key=lambda e: (e.pos, e.rank, e.order))
    out, cursor = [], 0
    for e in edits:
        out.append(text[cursor:e.pos])
        out.append(e.new)
        cursor = max(cursor, e.end) if e.rank else max(cursor, e.pos)
    out.append(text[cursor:])
    return "".join(out)


def unified_diff(original: str, enhanced: str, context: int = 2) -> str:
    if original == enhanced:
        return ""
    lines = difflib.unified_diff(
        original.splitlines(keepends=True), enhanced.splitlines(keepends=True),
        fromfile="original", tofile="enhanced", n=context,
    )
    return "".join(ln if ln.endswith("\n") else ln + "\n\\ No newline at end of file\n" for ln in lines)
