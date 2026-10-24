"""README templates: the sections a draft must have, taken from a Markdown file.

The default template is a copy of this repository's template/README.md; README_TEMPLATE
points at another file. The model is asked to follow the template, and conform() then
enforces its headings in code, because a small model sometimes drops or renames one.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TEMPLATE = Path(__file__).resolve().with_name("readme_template.md")
MAX_TEMPLATE_CHARS = 20000
TODO_LINE = "TODO: Add this section."
EXAMPLE_TODO_LINE = "TODO: Replace this template example with details of this project."
DIAGRAM_CAPTION = "*Generated from the code's imports: each arrow points from a file or folder to one it imports.*"

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})(.*)$")
# Template lines that are placeholders or examples: [Project Name], <project-slug>, "e.g., ...".
_EXAMPLE_RE = re.compile(r"\[[^\]\n]{3,}\](?!\()|<[a-z][\w]*-[\w-]*>|\be\.g\.|\bFeature \d+:")
_STOP_WORDS = {"and", "the", "a", "an", "of", "for", "to", "your"}


@dataclass(frozen=True)
class Heading:
    level: int
    title: str


def load_template() -> str:
    """Returns the README template: the file README_TEMPLATE names, or the bundled default."""
    path = Path(os.getenv("README_TEMPLATE") or DEFAULT_TEMPLATE).expanduser()
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:MAX_TEMPLATE_CHARS]
    except OSError as exc:
        raise ValueError(f"README_TEMPLATE could not be read: {path} ({exc.strerror or exc}).") from None


def headings(markdown: str) -> list[Heading]:
    """Lists the Markdown headings outside code blocks."""
    lines = markdown.splitlines()
    found = []
    for line, code in zip(lines, _code_mask(lines)):
        match = None if code else _HEADING_RE.match(line)
        if match:
            found.append(Heading(len(match.group(1)), match.group(2).strip()))
    return found


def conform(readme: str, template: str) -> str:
    """Gives the README the template's sections in order: renames reworded ones, adds missing ones as TODO."""
    wanted, top, sub = _structure(headings(template))
    if not wanted:
        return readme
    preamble, sections = _split(readme.splitlines(), top)
    matched = _match([title for title, _ in sections], [title for title, _ in wanted])
    by_draft = {draft: wanted_index for wanted_index, draft in matched.items()}
    extras, anchor = defaultdict(list), -1
    for draft, (_, lines) in enumerate(sections):
        if draft in by_draft:
            anchor = by_draft[draft]
        else:
            extras[anchor].append(lines)

    out = list(preamble)
    for lines in extras[-1]:
        out += lines
    for index, (title, subs) in enumerate(wanted):
        if index in matched:
            body = sections[matched[index]][1][1:]
            out += [f"{'#' * top} {title}"] + _conform_subsections(body, subs, sub)
        else:
            out += _todo_section(top, title)
            for sub_title in subs:
                out += _todo_section(sub, sub_title)
        for lines in extras[index]:
            out += lines
    return "\n".join(out).rstrip() + "\n"


def remove_copied_examples(readme: str, template: str) -> str:
    """Replaces lines the model copied word for word from the template's placeholders and examples."""
    examples = {
        line.strip() for line in template.splitlines()
        if len(line.strip()) >= 12 and _EXAMPLE_RE.search(line) and not _HEADING_RE.match(line.strip())
    }
    out = []
    for line in readme.splitlines():
        if line.strip() in examples:
            if out and out[-1] == EXAMPLE_TODO_LINE:
                continue
            line = EXAMPLE_TODO_LINE
        out.append(line)
    return "\n".join(out) + "\n"


def is_unfilled_template(readme: str, template: str) -> bool:
    """True when a project's README is still mostly the template's own text."""
    lines = {
        line.strip() for line in template.splitlines()
        if len(line.strip()) >= 25 and not line.strip().startswith(("#", "|", "```", "---"))
    }
    if len(lines) < 5:
        return False
    return len(lines & {line.strip() for line in readme.splitlines()}) >= 0.4 * len(lines)


def insert_diagram(readme: str, mermaid: str | None) -> str:
    """Puts the import diagram at the end of the architecture section, replacing any model-drawn one."""
    if not mermaid:
        return readme
    lines = readme.splitlines()
    mask = _code_mask(lines)
    for start, (line, code) in enumerate(zip(lines, mask)):
        match = None if code else _HEADING_RE.match(line)
        if not match or "architecture" not in match.group(2).lower():
            continue
        level = len(match.group(1))
        end = next(
            (i for i in range(start + 1, len(lines)) if not mask[i] and _heading_level(lines[i]) <= level),
            len(lines),
        )
        body = [line for line in _without_mermaid(lines[start + 1:end]) if line.strip() != DIAGRAM_CAPTION]
        while body and not body[-1].strip():
            body.pop()
        block = ["", DIAGRAM_CAPTION, "", "```mermaid", *mermaid.splitlines(), "```", ""]
        return "\n".join(lines[:start + 1] + body + block + lines[end:]).rstrip() + "\n"
    return readme


def _heading_level(line: str) -> int:
    match = _HEADING_RE.match(line)
    return len(match.group(1)) if match else 99


def _code_mask(lines: list[str]) -> list[bool]:
    """Marks the lines that belong to fenced code blocks, fences included."""
    mask, fence = [], None
    for line in lines:
        match = _FENCE_RE.match(line)
        if fence is None:
            if match:
                fence = match.group(1)
            mask.append(fence is not None)
        else:
            mask.append(True)
            if _closes(match, fence):
                fence = None
    return mask


def _closes(match: re.Match | None, fence: str) -> bool:
    return bool(match) and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence) and not match.group(2).strip()


def _without_mermaid(lines: list[str]) -> list[str]:
    out, skipping = [], None
    for line in lines:
        match = _FENCE_RE.match(line)
        if skipping:
            if _closes(match, skipping):
                skipping = None
            continue
        if match and match.group(2).strip().lower() == "mermaid":
            skipping = match.group(1)
            continue
        out.append(line)
    return out


def _structure(heads: list[Heading]) -> tuple[list[tuple[str, list[str]]], int, int]:
    """Returns the template's sections with their sub-section titles, and the two heading levels."""
    body = heads[1:] if heads and heads[0].level == 1 else heads
    if not body:
        return [], 2, 3
    top = min(heading.level for heading in body)
    wanted: list[tuple[str, list[str]]] = []
    for heading in body:
        if heading.level == top:
            wanted.append((heading.title, []))
        elif heading.level == top + 1 and wanted:
            wanted[-1][1].append(heading.title)
    return wanted, top, top + 1


def _split(lines: list[str], level: int) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """Splits Markdown at headings of one level: the lines before the first, then (title, lines) each."""
    preamble: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    for line, code in zip(lines, _code_mask(lines)):
        match = None if code else _HEADING_RE.match(line)
        if match and len(match.group(1)) == level:
            sections.append((match.group(2).strip(), [line]))
        elif sections:
            sections[-1][1].append(line)
        else:
            preamble.append(line)
    return preamble, sections


def _conform_subsections(body: list[str], subs: list[str], level: int) -> list[str]:
    if not subs:
        return body
    intro, parts = _split(body, level)
    matched = _match([title for title, _ in parts], subs)
    by_draft = {draft: index for index, draft in matched.items()}
    out = list(intro)
    for draft, (_, lines) in enumerate(parts):
        out += ([f"{'#' * level} {subs[by_draft[draft]]}"] + lines[1:]) if draft in by_draft else lines
    for index, title in enumerate(subs):
        if index not in matched:
            out += _todo_section(level, title)
    return out


def _todo_section(level: int, title: str) -> list[str]:
    return ["", f"{'#' * level} {title}", "", TODO_LINE, ""]


def _match(found: list[str], wanted: list[str]) -> dict[int, int]:
    """Pairs template titles with the draft's: same words first, then shortened or reworded ones."""
    matched: dict[int, int] = {}
    for same in (_same_words, _contained_words, _same_first_word):
        for draft, title in enumerate(found):
            if draft in matched.values():
                continue
            options = [index for index, w in enumerate(wanted) if index not in matched and same(title, w)]
            if len(options) == 1 or (options and same is _same_words):
                matched[options[0]] = draft
    return matched


def _words(title: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", title.lower().replace("&", " and "))
    return [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words if w not in _STOP_WORDS]


def _same_words(a: str, b: str) -> bool:
    return _words(a) == _words(b)


def _contained_words(a: str, b: str) -> bool:
    x, y = set(_words(a)), set(_words(b))
    return bool(x and y) and (x <= y or y <= x)


def _same_first_word(a: str, b: str) -> bool:
    x, y = _words(a), _words(b)
    return bool(x and y) and x[0] == y[0]
