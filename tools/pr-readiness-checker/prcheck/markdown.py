"""Just enough Markdown parsing for README checks: level-2 sections and code fences."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_FENCE = re.compile(r"^\s*(```|~~~)")
_H2 = re.compile(r"^##\s+(.+?)\s*#*\s*$")


@dataclass
class Section:
    title: str
    line: int  # 1-based line of the heading
    body: list[str] = field(default_factory=list)


@dataclass
class ParsedMarkdown:
    lines: list[str]
    sections: list[Section]
    in_code: list[bool]  # in_code[i] is True when lines[i] is inside a code fence


def parse(text: str) -> ParsedMarkdown:
    lines = text.splitlines()
    sections: list[Section] = []
    in_code: list[bool] = []
    fenced = False
    for number, line in enumerate(lines, start=1):
        if _FENCE.match(line):
            in_code.append(True)
            fenced = not fenced
            if sections:
                sections[-1].body.append(line)
            continue
        in_code.append(fenced)
        heading = None if fenced else _H2.match(line)
        if heading:
            sections.append(Section(title=heading.group(1).strip(), line=number))
        elif sections:
            sections[-1].body.append(line)
    return ParsedMarkdown(lines=lines, sections=sections, in_code=in_code)


def normalize_heading(title: str) -> str:
    """'Security & Privacy Considerations' -> 'security and privacy considerations'."""
    title = title.lower().replace("&", " and ")
    title = re.sub(r"[^a-z0-9]+", " ", title)
    return " ".join(title.split())


def normalize_line(line: str) -> str:
    return " ".join(line.strip().split())


def contains_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None
