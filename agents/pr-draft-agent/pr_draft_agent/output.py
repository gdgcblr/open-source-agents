"""Structural validation and deterministic rendering of the final PR draft."""

from __future__ import annotations

import re

from pr_draft_agent.repository import RepositorySnapshot

MAX_OUTPUT_BYTES = 16_384
VERIFICATION_NOTICE = (
    "Verification: This agent inspected staged changes only. It did not execute tests "
    "or verify runtime behavior. Review the draft and complete the checklist before submitting."
)

# C0 and C1 controls, plus DEL, except newline and tab.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
# CommonMark fenced-code opener: up to three spaces, then three or more backticks or tildes.
_FENCE_OPEN_RE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
_BLANK_LINE_RE = re.compile(r"\n[ \t]*\n")
# A checked Markdown task marker only at a list-item start.
_TASK_RE = re.compile(
    r"^([ \t]*(?:>[ \t]*)*(?:[-+*]|\d{1,9}[.)])[ \t]+)\[([xX])\](?=[ \t]|$)"
)


class OutputError(Exception):
    """An invalid model draft with a stable code and a content-free message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _line_offsets(text: str):
    offset = 0
    for line in text.split("\n"):
        yield offset, line
        offset += len(line) + 1


def _fence_ranges(text: str) -> list[tuple[int, int]]:
    """Return protected fenced-code ranges, rejecting an unclosed fence."""
    lines = list(_line_offsets(text))
    ranges: list[tuple[int, int]] = []
    index = 0

    while index < len(lines):
        offset, line = lines[index]
        opener = _FENCE_OPEN_RE.match(line)
        if opener is None:
            index += 1
            continue

        fence = opener.group("fence")
        fence_char = fence[0]
        info = opener.group("info")
        if fence_char == "`" and "`" in info:
            index += 1
            continue

        fence_length = len(fence)
        closing = index + 1
        while closing < len(lines):
            candidate = lines[closing][1]
            stripped = candidate.lstrip(" ")
            indent = len(candidate) - len(stripped)
            run = len(stripped) - len(stripped.lstrip(fence_char))
            if (
                indent <= 3
                and run >= fence_length
                and not stripped[run:].strip()
            ):
                end_offset = lines[closing][0] + len(candidate)
                ranges.append((offset, end_offset))
                index = closing + 1
                break
            closing += 1
        else:
            raise OutputError(
                "INVALID_DRAFT", "The draft contains an unclosed code fence."
            )

    return ranges


def _free_ranges(text: str, protected: list[tuple[int, int]]) -> list[tuple[int, int]]:
    free: list[tuple[int, int]] = []
    cursor = 0
    for start, end in protected:
        if cursor < start:
            free.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < len(text):
        free.append((cursor, len(text)))
    return free


def _paragraph_ranges(text: str, start: int, end: int) -> list[tuple[int, int]]:
    paragraphs: list[tuple[int, int]] = []
    cursor = start
    for match in _BLANK_LINE_RE.finditer(text, start, end):
        if cursor < match.start():
            paragraphs.append((cursor, match.start()))
        cursor = match.end()
    if cursor < end:
        paragraphs.append((cursor, end))
    return paragraphs


def _run_length(text: str, start: int, end: int) -> int:
    cursor = start
    while cursor < end and text[cursor] == "`":
        cursor += 1
    return cursor - start


def _escaped(text: str, index: int, floor: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= floor and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _next_exact_run(text: str, start: int, end: int, length: int) -> int | None:
    cursor = start
    while cursor < end:
        found = text.find("`", cursor, end)
        if found == -1:
            return None
        run = _run_length(text, found, end)
        if run == length:
            return found
        cursor = found + run
    return None


def _inline_ranges(
    text: str, start: int, end: int
) -> list[tuple[int, int]]:
    """Return inline code-span ranges; unmatched backtick runs stay literal."""
    ranges: list[tuple[int, int]] = []
    cursor = start

    while cursor < end:
        opener = text.find("`", cursor, end)
        if opener == -1:
            break
        if _escaped(text, opener, start):
            cursor = opener + 1
            continue

        length = _run_length(text, opener, end)
        closer = _next_exact_run(text, opener + length, end, length)
        if closer is None:
            cursor = opener + length
            continue

        ranges.append((opener, closer + length))
        cursor = closer + length

    return ranges


def _protected_ranges(text: str) -> list[tuple[int, int]]:
    fences = _fence_ranges(text)
    inline: list[tuple[int, int]] = []
    for start, end in _free_ranges(text, fences):
        for paragraph_start, paragraph_end in _paragraph_ranges(text, start, end):
            inline.extend(_inline_ranges(text, paragraph_start, paragraph_end))
    return sorted(fences + inline)


def _inside(position: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in ranges)


def _overlaps(
    start: int, end: int, ranges: list[tuple[int, int]]
) -> bool:
    return any(start < range_end and end > range_start for range_start, range_end in ranges)


def _normalize_task_markers(text: str, protected: list[tuple[int, int]]) -> str:
    """Uncheck task markers outside code, preserving indentation and bullets."""
    lines: list[str] = []
    offset = 0
    for line in text.split("\n"):
        if _inside(offset, protected):
            lines.append(line)
        else:
            lines.append(_TASK_RE.sub(r"\1[ ]", line))
        offset += len(line) + 1
    return "\n".join(lines)


def _remove_unprotected_notice(text: str, protected: list[tuple[int, int]]) -> str:
    """Remove model-echoed notices outside code; keep application-owned code."""
    pieces: list[str] = []
    cursor = 0
    while True:
        found = text.find(VERIFICATION_NOTICE, cursor)
        if found == -1:
            pieces.append(text[cursor:])
            break
        end = found + len(VERIFICATION_NOTICE)
        if _overlaps(found, end, protected):
            pieces.append(text[cursor:end])
        else:
            pieces.append(text[cursor:found])
        cursor = end
    return "".join(pieces)


def validate_and_render(text: str, snapshot: RepositorySnapshot) -> str:
    """Validate a model draft, uncheck task markers, and append the fixed notice.

    The snapshot is part of the shared contract but structural checks do not need it.
    The result ends with the notice and has no trailing newline; the CLI adds exactly one.
    """
    del snapshot

    if not text.strip():
        raise OutputError("INVALID_DRAFT", "The model returned an empty draft.")
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        raise OutputError(
            "INVALID_DRAFT", "The draft is not valid UTF-8 text."
        ) from None
    if _CONTROL_RE.search(text):
        raise OutputError("INVALID_DRAFT", "The draft contains terminal control characters.")

    lines = text.split("\n")
    first = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first is None:
        raise OutputError("INVALID_DRAFT", "The model returned an empty draft.")

    title = lines[first]
    if not title.startswith("# ") or not title[2:].strip():
        raise OutputError(
            "INVALID_DRAFT", "The draft must start with a nonempty '# ' title."
        )

    body = "\n".join(lines[first + 1 :])
    if not body.strip():
        raise OutputError(
            "INVALID_DRAFT", "The draft must include a description after the title."
        )

    protected = _protected_ranges(body)
    if any(not _inside(match.start(), protected) for match in re.finditer(r"<!--", body)):
        raise OutputError("INVALID_DRAFT", "The draft contains an HTML comment.")
    body = _normalize_task_markers(body, protected)
    body = _remove_unprotected_notice(body, protected).rstrip()
    if not body.strip():
        raise OutputError(
            "INVALID_DRAFT", "The draft must include a description after the title."
        )

    rendered = f"{title}\n{body}\n\n{VERIFICATION_NOTICE}"
    try:
        rendered_bytes = (rendered + "\n").encode("utf-8")
    except UnicodeEncodeError:
        raise OutputError("INVALID_DRAFT", "The draft contains invalid Unicode text.") from None
    if len(rendered_bytes) > MAX_OUTPUT_BYTES:
        raise OutputError(
            "OUTPUT_TOO_LARGE",
            f"The draft exceeds the {MAX_OUTPUT_BYTES}-byte rendered output limit.",
        )
    return rendered
