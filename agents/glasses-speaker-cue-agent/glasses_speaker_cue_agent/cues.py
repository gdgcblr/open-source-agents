"""Turns script text into sections and short, glanceable cues.

Ported from NeuralLens-AI `lib/features/scripts/util/cue_segmenter.dart`, so
`script.md` produced here splits the same way inside the NeuralLens app.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import MAX_CUE_CHARS

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")
# "।" is the danda used as a full stop in Hindi, Marathi and Bengali.
_SENTENCE_BREAK = re.compile(r"(?<=[.!?…।])\s+")
_CLAUSE_BREAK = re.compile(r"(?<=[,;:—–])\s+")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class Section:
    heading: str
    spoken_text: str


@dataclass(frozen=True)
class Cue:
    index: int
    section_index: int
    heading: str
    text: str


def sections_from_body(body: str) -> list[Section]:
    """Splits on `## Heading` lines; without headings, each paragraph is a section."""
    lines = body.replace("\r\n", "\n").split("\n")
    has_headings = any(_HEADING.match(line) for line in lines)

    sections: list[Section] = []
    heading = ""
    paragraphs: list[str] = []
    current: list[str] = []

    def end_paragraph() -> None:
        text = _WHITESPACE.sub(" ", " ".join(current)).strip()
        if text:
            paragraphs.append(text)
        current.clear()

    def end_section() -> None:
        end_paragraph()
        if has_headings:
            text = "\n\n".join(paragraphs)
            if text:
                sections.append(Section(heading, text))
        else:
            sections.extend(Section("", p) for p in paragraphs)
        paragraphs.clear()

    for line in lines:
        match = _HEADING.match(line)
        if match:
            end_section()
            heading = match.group(1).strip()
        elif not line.strip():
            end_paragraph()
        else:
            current.append(line.strip())
    end_section()
    return sections


def body_from_sections(sections: list[Section]) -> str:
    """Inverse of `sections_from_body`."""
    return "\n\n".join(
        f"## {s.heading.strip()}\n{s.spoken_text.strip()}"
        if s.heading.strip()
        else s.spoken_text.strip()
        for s in sections
    )


def chunk(text: str, max_chars: int = MAX_CUE_CHARS) -> list[str]:
    """Packs sentences into chunks of at most `max_chars`.

    Over-long sentences are split on clause boundaries, then on words. A single
    word longer than `max_chars` is the only way a chunk can exceed the limit.
    """
    normalized = _WHITESPACE.sub(" ", text).strip()
    if not normalized:
        return []

    pieces: list[str] = []
    for sentence in _SENTENCE_BREAK.split(normalized):
        if len(sentence) <= max_chars:
            pieces.append(sentence)
            continue
        for clause in _CLAUSE_BREAK.split(sentence):
            if len(clause) <= max_chars:
                pieces.append(clause)
            else:
                pieces.extend(_pack_words(clause.split(" "), max_chars))
    return _pack_words(pieces, max_chars)


def cues(sections: list[Section], max_chars: int = MAX_CUE_CHARS) -> list[Cue]:
    """Splits every section into cues, numbered across the whole script."""
    out: list[Cue] = []
    for i, section in enumerate(sections):
        heading = section.heading.strip() or f"Part {i + 1}"
        for text in chunk(section.spoken_text, max_chars):
            out.append(Cue(index=len(out), section_index=i, heading=heading, text=text))
    return out


def _pack_words(parts: list[str], max_chars: int) -> list[str]:
    out: list[str] = []
    line = ""
    for part in parts:
        if not part:
            continue
        if not line:
            line = part
        elif len(line) + 1 + len(part) <= max_chars:
            line = f"{line} {part}"
        else:
            out.append(line)
            line = part
    if line:
        out.append(line)
    return out
