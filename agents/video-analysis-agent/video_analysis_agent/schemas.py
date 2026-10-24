"""Pydantic models for the transcript, the LLM analysis, and the final report."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


def format_timestamp(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


# ---------------------------------------------------------------- transcript


class TranscriptSegment(_Base):
    start: float
    end: float
    text: str
    low_confidence: bool = False


class Transcript(_Base):
    language: Optional[str] = None
    duration: float = 0.0
    source: Optional[str] = None
    segments: list[TranscriptSegment] = Field(default_factory=list)


# ------------------------------------------------------------------ analysis


class Evidenced(_Base):
    """An item backed by a verbatim transcript quote.

    `timestamp` ("HH:MM:SS") is overwritten by the validator with the time of the
    segment where the quote was actually found.
    """

    quote: str = Field(min_length=1)
    timestamp: Optional[str] = None


class KeyPoint(Evidenced):
    point: str = Field(min_length=1)


class Decision(Evidenced):
    """Something the speakers clearly agreed on or finalized."""

    decision: str = Field(min_length=1)


class Proposal(Evidenced):
    """Suggested or floated, but NOT agreed on."""

    suggestion: str = Field(min_length=1)
    proposed_by: Optional[str] = None


class ActionItem(Evidenced):
    task: str = Field(min_length=1)
    owner: Optional[str] = None  # only if a person is named in the transcript
    deadline: Optional[str] = None  # only if stated in the transcript


class Fact(Evidenced):
    kind: Literal["name", "date", "number", "other"] = "other"
    value: str = Field(min_length=1)
    context: str = ""


class OpenQuestion(Evidenced):
    question: str = Field(min_length=1)


class Insight(_Base):
    """Model-generated analysis. NOT stated in the video; quote is optional."""

    text: str = Field(min_length=1)
    kind: Literal["insight", "conclusion", "next_step"] = "insight"
    quote: Optional[str] = None
    timestamp: Optional[str] = None


class Analysis(_Base):
    summary: str = ""
    key_points: list[KeyPoint] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    proposals: list[Proposal] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    insights: list[Insight] = Field(default_factory=list)


# Analysis list fields -> item model (used for lenient, per-item parsing).
LIST_FIELDS: dict[str, type[_Base]] = {
    "key_points": KeyPoint,
    "decisions": Decision,
    "proposals": Proposal,
    "action_items": ActionItem,
    "facts": Fact,
    "open_questions": OpenQuestion,
    "insights": Insight,
}


# -------------------------------------------------------------------- report


class ReportMeta(_Base):
    source: str
    generated_at: str
    duration: float = 0.0
    language: Optional[str] = None
    llm_provider: str = ""
    llm_model: str = ""
    whisper_model: Optional[str] = None
    audio_preprocessing: list[str] = Field(default_factory=list)


class Report(_Base):
    meta: ReportMeta
    analysis: Analysis
    warnings: list[str] = Field(default_factory=list)
    transcript: Transcript
