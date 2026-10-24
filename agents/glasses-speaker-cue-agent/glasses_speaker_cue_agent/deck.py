"""The output contract: the model's draft in, a validated cue deck out.

`Deck` is a superset of NeuralLens-AI's `GeneratedScript` JSON (`title`,
`estimatedDurationSeconds`, `sections`), so the app can read it unchanged.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field, ValidationError

from . import cues, duration
from .config import DURATION_TOLERANCE, MAX_CUE_CHARS, QA_COUNT


class DraftError(ValueError):
    """The model's reply was not a usable script."""


class DraftSection(BaseModel):
    heading: str = ""
    spokenText: str = Field(min_length=1)
    cueKeywords: list[str] = Field(default_factory=list)


class QA(BaseModel):
    question: str
    answer: str
    fromNotes: bool = False


class Draft(BaseModel):
    title: str = "Untitled talk"
    sections: list[DraftSection] = Field(min_length=1)
    qa: list[QA] = Field(default_factory=list)


class DeckCue(BaseModel):
    index: int
    sectionIndex: int
    heading: str
    text: str
    sayBy: int
    sayByLabel: str
    flags: list[str] = Field(default_factory=list)


class Deck(BaseModel):
    title: str
    estimatedDurationSeconds: int
    targetSeconds: int
    fitsTarget: bool
    language: str
    sections: list[DraftSection]
    cues: list[DeckCue]
    qa: list[QA]
    warnings: list[str] = Field(default_factory=list)


def parse_draft(raw: str) -> Draft:
    """Parses the model reply, tolerating code fences or prose around the JSON."""
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise DraftError("Reply did not contain a JSON object.")
    try:
        data = json.loads(raw[start : end + 1])
        return Draft.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise DraftError(f"Reply JSON did not match the expected shape: {exc}") from exc


def build_deck(draft: Draft, target_seconds: int, language: str, include_qa: bool = True) -> Deck:
    """Re-splits the script into lens-sized cues and times them in code.

    The model's own line breaks are never trusted: every cue comes from
    `cues.chunk`, so each one is at most MAX_CUE_CHARS characters. Q&A is
    dropped when not requested and capped at QA_COUNT, whatever the model sent.
    """
    sections = [
        cues.Section(s.heading.strip() or f"Part {i + 1}", s.spokenText.strip())
        for i, s in enumerate(draft.sections)
    ]
    split = cues.cues(sections, MAX_CUE_CHARS)
    marks = duration.say_by([c.text for c in split])
    seconds = duration.estimate_seconds(" ".join(s.spoken_text for s in sections))

    warnings: list[str] = []
    on_time = duration.fits_target(seconds, target_seconds)
    if not on_time:
        warnings.append(
            f"Estimated {duration.format_seconds(seconds)} vs target "
            f"{duration.format_seconds(target_seconds)} (outside ±{DURATION_TOLERANCE:.0%})."
        )

    return Deck(
        title=draft.title.strip() or "Untitled talk",
        estimatedDurationSeconds=seconds,
        targetSeconds=target_seconds,
        fitsTarget=on_time,
        language=language,
        sections=[
            DraftSection(heading=s.heading, spokenText=s.spoken_text, cueKeywords=d.cueKeywords)
            for s, d in zip(sections, draft.sections, strict=True)
        ],
        cues=[
            DeckCue(
                index=c.index,
                sectionIndex=c.section_index,
                heading=c.heading,
                text=c.text,
                sayBy=mark,
                sayByLabel=duration.format_seconds(mark),
            )
            for c, mark in zip(split, marks, strict=True)
        ],
        qa=draft.qa[:QA_COUNT] if include_qa else [],
        warnings=warnings,
    )


def to_script_markdown(deck: Deck) -> str:
    """`## Heading` sections, the format the NeuralLens editor splits into cues."""
    body = cues.body_from_sections([cues.Section(s.heading, s.spokenText) for s in deck.sections])
    if deck.qa:
        qa_lines = "\n\n".join(f"Q: {item.question}\nA: {item.answer}" for item in deck.qa)
        body += f"\n\n## Q&A\n{qa_lines}"
    return body + "\n"
