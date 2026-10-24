"""LLM analysis: chunk long transcripts, extract structure, merge, then validate."""

from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from .errors import AnalysisError, LLMError
from .llm import LLMClient, extract_json
from .schemas import LIST_FIELDS, Analysis, Transcript, TranscriptSegment, format_timestamp
from .validate import coerce_analysis, verify_analysis

log = logging.getLogger(__name__)

DEFAULT_CHUNK_CHARS = 12000
OVERLAP_SEGMENTS = 2

SYSTEM_PROMPT = """You analyze transcripts of recorded videos (meetings, lectures, talks).
Reply with ONE JSON object only, no prose.

STRICT RULES - never invent anything:
- Use only what is stated in the transcript. If something is not stated, omit it or use null.
- Every item except "insights" MUST include "quote": a short VERBATIM copy (max ~30 words) from the
  transcript, without the [HH:MM:SS] prefix, and "timestamp": that line's [HH:MM:SS].
- "decisions": ONLY things clearly agreed or finalized. Ideas like "we could", "maybe", "I suggest"
  go in "proposals" instead, never in "decisions".
- "action_items": someone is assigned or commits to a task. "owner" only if a person is NAMED in the
  transcript (never guess from roles or pronouns); otherwise null. "deadline" only if a date/time is
  stated (copy the wording); otherwise null.
- "facts": names, dates, numbers and figures explicitly stated. "kind" is one of name|date|number|other.
- "open_questions": questions raised but not answered, or discussions left unresolved.
- "insights": your own analysis (kind: insight | conclusion | next_step). These are inferences, not
  statements from the video; max 5; "quote"/"timestamp" optional.
- Lines tagged (low confidence) may be mistranscribed. Do not base names, numbers, decisions or
  action items on them alone.
- Empty categories must be empty lists. Do not pad.

JSON shape:
{"summary": "...",
 "key_points": [{"point": "...", "timestamp": "HH:MM:SS", "quote": "..."}],
 "decisions": [{"decision": "...", "timestamp": "...", "quote": "..."}],
 "proposals": [{"suggestion": "...", "proposed_by": null, "timestamp": "...", "quote": "..."}],
 "action_items": [{"task": "...", "owner": null, "deadline": null, "timestamp": "...", "quote": "..."}],
 "facts": [{"kind": "number", "value": "...", "context": "...", "timestamp": "...", "quote": "..."}],
 "open_questions": [{"question": "...", "timestamp": "...", "quote": "..."}],
 "insights": [{"text": "...", "kind": "next_step", "timestamp": null, "quote": null}]}"""

MERGE_SYSTEM = (
    "You merge summaries of consecutive parts of one video into one coherent summary "
    '(max 200 words). Use only the given text; add nothing. Reply with JSON: {"summary": "..."}'
)


def format_line(seg: TranscriptSegment) -> str:
    flag = " (low confidence)" if seg.low_confidence else ""
    return f"[{format_timestamp(seg.start)}]{flag} {seg.text}"


def chunk_segments(segments: list[TranscriptSegment], max_chars: int = DEFAULT_CHUNK_CHARS) -> list[list[TranscriptSegment]]:
    """Split into windows of ~max_chars, overlapping a few segments so context isn't cut."""
    chunks: list[list[TranscriptSegment]] = []
    current: list[TranscriptSegment] = []
    size = 0
    for seg in segments:
        line_len = len(format_line(seg)) + 1
        if current and size + line_len > max_chars:
            chunks.append(current)
            current = current[-OVERLAP_SEGMENTS:]
            size = sum(len(format_line(s)) + 1 for s in current)
        current.append(seg)
        size += line_len
    if current:
        chunks.append(current)
    return chunks


def _ask(llm: LLMClient, system: str, user: str) -> dict:
    """One LLM call returning a JSON object; one repair retry on unparseable output."""
    prompt = user
    for attempt in (1, 2):
        text = llm.complete_json(system, prompt)
        try:
            data = extract_json(text)
            if isinstance(data, dict):
                return data
            error = "top-level value is not a JSON object"
        except json.JSONDecodeError as exc:
            error = str(exc)
        log.warning("LLM returned invalid JSON (%s)%s", error, "; retrying" if attempt == 1 else "")
        prompt = user + f"\n\nYour previous reply was not valid JSON ({error}). Reply with the JSON object only."
    raise AnalysisError("The LLM did not return valid JSON after a retry.")


def _analyze_chunk(llm: LLMClient, segments: list[TranscriptSegment], part: int, parts: int) -> tuple[Analysis, list[str]]:
    header = f"This is part {part} of {parts} of a longer transcript; analyze only this part.\n\n" if parts > 1 else ""
    user = header + "TRANSCRIPT:\n" + "\n".join(format_line(s) for s in segments)
    return coerce_analysis(_ask(llm, SYSTEM_PROMPT, user))


def analyze(transcript: Transcript, llm: LLMClient, max_chars: int = DEFAULT_CHUNK_CHARS) -> tuple[Analysis, list[str]]:
    """Run the full analysis. Returns a validated Analysis plus warnings."""
    chunks = chunk_segments(transcript.segments, max_chars)
    if not chunks:
        raise AnalysisError("Transcript is empty.")
    log.info("Analyzing transcript in %d part(s) with %s/%s...", len(chunks), llm.provider, llm.model)

    warnings: list[str] = []
    partials: list[Analysis] = []
    for i, chunk in enumerate(chunks, 1):
        try:
            partial, w = _analyze_chunk(llm, chunk, i, len(chunks))
        except (AnalysisError, LLMError) as exc:
            if len(chunks) == 1:
                raise
            warnings.append(f"Part {i}/{len(chunks)} could not be analyzed and is missing from the report: {exc}")
            continue
        partials.append(partial)
        warnings += w
    if not partials:
        raise AnalysisError("Every part of the transcript failed to analyze.")

    merged: dict = {name: [item for p in partials for item in getattr(p, name)] for name in LIST_FIELDS}
    summaries = [p.summary for p in partials if p.summary]
    if len(partials) == 1 or not summaries:
        merged["summary"] = summaries[0] if summaries else ""
    else:
        try:
            data = _ask(llm, MERGE_SYSTEM, "\n\n".join(f"Part {i}: {s}" for i, s in enumerate(summaries, 1)))
            merged["summary"] = str(data.get("summary") or "").strip() or "\n\n".join(summaries)
        except (AnalysisError, LLMError) as exc:
            warnings.append(f"Could not merge part summaries ({exc}); showing them concatenated.")
            merged["summary"] = "\n\n".join(summaries)

    try:
        analysis = Analysis(**merged)
    except ValidationError as exc:  # unreachable in practice; items are already validated
        raise AnalysisError(f"Merged analysis invalid: {exc}") from exc
    analysis, verify_warnings = verify_analysis(analysis, transcript)
    return analysis, warnings + verify_warnings
