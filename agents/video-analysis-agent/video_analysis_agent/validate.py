"""Output validation: keep only what the transcript actually supports.

Two stages:
1. `coerce_analysis` - lenient structural parsing of raw LLM JSON with Pydantic;
   malformed items are dropped (with a warning) instead of failing the whole run.
2. `verify_analysis` - every evidenced item must quote the transcript. Items whose
   quote cannot be found are dropped; timestamps are taken from where the quote was
   found; owners/deadlines not present near the quote are removed.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from typing import Any, Optional

from pydantic import ValidationError

from .errors import AnalysisError
from .schemas import (
    LIST_FIELDS,
    Analysis,
    Transcript,
    TranscriptSegment,
    format_timestamp,
)

_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)
FUZZY_COVERAGE = 0.8
CONTEXT_SEGMENTS = 3  # segments around a quote searched for owner/deadline


def normalize(text: str) -> str:
    return _NON_WORD.sub(" ", text.lower()).strip()


# ------------------------------------------------------------- stage 1: parse


def coerce_analysis(data: Any) -> tuple[Analysis, list[str]]:
    if not isinstance(data, dict):
        raise AnalysisError("LLM output is not a JSON object.")
    warnings: list[str] = []
    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = ""
        warnings.append("LLM returned no summary.")
    fields: dict[str, Any] = {"summary": summary}
    for name, model in LIST_FIELDS.items():
        raw_items = data.get(name) or []
        if not isinstance(raw_items, list):
            warnings.append(f"'{name}' was not a list; ignored.")
            continue
        valid = []
        for raw in raw_items:
            try:
                valid.append(model.model_validate(raw))
            except ValidationError:
                warnings.append(f"Dropped malformed item in '{name}'.")
        fields[name] = valid
    return Analysis(**fields), warnings


# ---------------------------------------------------------- stage 2: evidence


class TranscriptIndex:
    def __init__(self, segments: list[TranscriptSegment]):
        self.segments = segments
        self.norm = [normalize(s.text) for s in segments]
        self.tokens = [set(n.split()) for n in self.norm]
        self.offsets: list[int] = []
        pos = 0
        for n in self.norm:
            self.offsets.append(pos)
            pos += len(n) + 1
        self.full = " ".join(self.norm)

    def locate(self, quote: str) -> Optional[int]:
        """Index of the segment where `quote` starts, or None if unsupported."""
        q = normalize(quote)
        if not q or not self.segments:
            return None
        i = self.full.find(q)
        while i != -1:
            end = i + len(q)
            if (i == 0 or self.full[i - 1] == " ") and (
                end == len(self.full) or self.full[end] == " "
            ):
                return max(0, bisect_right(self.offsets, i) - 1)
            i = self.full.find(q, i + 1)
        return self._fuzzy(q)

    def _fuzzy(self, q: str) -> Optional[int]:
        """Tolerate small wording drift: most quote words within 3 adjacent segments."""
        qset = set(q.split())
        if len(qset) < 3:
            return None
        best, best_score = None, (0.0, 0)
        for i in range(len(self.segments)):
            window = set().union(*self.tokens[i : i + 3])
            # Ties on coverage go to the window whose first segment holds the quote's start.
            score = (len(qset & window) / len(qset), len(qset & self.tokens[i]))
            if score > best_score:
                best, best_score = i, score
        return best if best_score[0] >= FUZZY_COVERAGE else None

    def context_tokens(self, idx: int) -> set[str]:
        lo, hi = max(0, idx - CONTEXT_SEGMENTS), idx + CONTEXT_SEGMENTS + 1
        return set().union(*self.tokens[lo:hi])

    def timestamp(self, idx: int) -> str:
        return format_timestamp(self.segments[idx].start)


def _supported(phrase: str, context: set[str]) -> bool:
    tokens = normalize(phrase).split()
    return bool(tokens) and all(t in context for t in tokens)


def _dedupe(items: list, key) -> list:
    seen, out = set(), []
    for item in items:
        k = normalize(key(item))
        if k not in seen:
            seen.add(k)
            out.append(item)
    return out


def verify_analysis(analysis: Analysis, transcript: Transcript) -> tuple[Analysis, list[str]]:
    index = TranscriptIndex(transcript.segments)
    warnings: list[str] = []
    result: dict[str, Any] = {"summary": analysis.summary}

    for name in LIST_FIELDS:
        if name == "insights":
            continue
        kept = []
        for item in getattr(analysis, name):
            idx = index.locate(item.quote)
            if idx is None:
                warnings.append(f"Dropped unsupported {name} item (quote not in transcript): {item.quote[:80]!r}")
                continue
            item.timestamp = index.timestamp(idx)
            if name == "action_items":
                context = index.context_tokens(idx)
                if item.owner and not _supported(item.owner, context):
                    warnings.append(f"Removed unsupported owner {item.owner!r} from task {item.task[:50]!r}.")
                    item.owner = None
                if item.deadline and not _supported(item.deadline, context):
                    warnings.append(f"Removed unsupported deadline {item.deadline!r} from task {item.task[:50]!r}.")
                    item.deadline = None
            kept.append(item)
        result[name] = kept

    insights = []
    for ins in analysis.insights:
        if ins.quote:
            idx = index.locate(ins.quote)
            ins.timestamp = index.timestamp(idx) if idx is not None else None
            if idx is None:
                ins.quote = None
        else:
            ins.timestamp = None
        insights.append(ins)
    result["insights"] = insights

    result["key_points"] = _dedupe(result["key_points"], lambda x: x.point)
    result["decisions"] = _dedupe(result["decisions"], lambda x: x.decision)
    result["proposals"] = _dedupe(result["proposals"], lambda x: x.suggestion)
    result["action_items"] = _dedupe(result["action_items"], lambda x: x.task)
    result["facts"] = _dedupe(result["facts"], lambda x: f"{x.kind} {x.value}")
    result["open_questions"] = _dedupe(result["open_questions"], lambda x: x.question)
    result["insights"] = _dedupe(result["insights"], lambda x: x.text)

    for name in LIST_FIELDS:
        if name not in ("insights",):
            result[name].sort(key=lambda x: x.timestamp or "")
    return Analysis(**result), warnings
