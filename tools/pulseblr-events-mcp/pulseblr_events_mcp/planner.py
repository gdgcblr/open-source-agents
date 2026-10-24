"""Bounded exact event scheduling under explicit duration and transfer rules."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import combinations

from .discovery import _clock, _events, _format, _interests, _rank, _timestamp
from .errors import InputError


@dataclass(frozen=True)
class _Candidate:
    event: dict
    start: datetime
    end: datetime
    score: float
    matched: list[str]
    estimated: bool


def _minutes(value, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= 1440:
        raise InputError(f"{name} must be an integer from {minimum} to 1440")
    return value


def _compatible(left: _Candidate, right: _Candidate, physical_buffer: int) -> bool:
    if (right.start, right.event["id"]) < (left.start, left.event["id"]):
        left, right = right, left
    online_only = (
        _format(left.event.get("format")) == _format(right.event.get("format")) == "online"
    )
    buffer = 5 if online_only else physical_buffer
    return right.start - left.end >= timedelta(minutes=buffer)


def plan_schedule(
    events: list[dict],
    interests: list[str] | None = None,
    max_events: int = 2,
    transfer_buffer_minutes: int = 60,
    duration_policy: str = "strict",
    assumed_duration_minutes: int | None = None,
    now: datetime | None = None,
) -> dict:
    """Choose the highest-scoring feasible chronological subset of at most three."""
    clock = _clock(now)
    if isinstance(max_events, bool) or not isinstance(max_events, int) or not 1 <= max_events <= 3:
        raise InputError("max_events must be an integer from 1 to 3")
    transfer_buffer_minutes = _minutes(transfer_buffer_minutes, "transfer_buffer_minutes")
    if not isinstance(duration_policy, str) or duration_policy not in {"strict", "estimate"}:
        raise InputError("duration_policy must be strict or estimate")
    if duration_policy == "estimate":
        assumed_duration_minutes = _minutes(
            assumed_duration_minutes, "assumed_duration_minutes", minimum=1
        )
    elif assumed_duration_minutes is not None:
        raise InputError("assumed_duration_minutes requires duration_policy='estimate'")
    wanted = _interests(interests)
    unique, warnings = _events(events, maximum=50)
    candidates: list[_Candidate] = []
    not_selected = []
    needs_duration = []
    for event in unique:
        start = _timestamp(event.get("startsAt"))
        if start is None:
            not_selected.append({"event": event, "reason_code": "invalid_start"})
            continue
        if start < clock:
            not_selected.append({"event": event, "reason_code": "already_started"})
            continue
        end = _timestamp(event.get("endsAt"))
        estimated = end is None or end <= start
        if estimated:
            if duration_policy == "strict":
                detail = (
                    "invalid_end"
                    if event.get("endsAt") or event.get("endTimeStatus") == "invalid"
                    else "missing_end"
                )
                needs_duration.append({"event": event, "reason_code": detail})
                not_selected.append({"event": event, "reason_code": "needs_duration"})
                continue
            try:
                end = start + timedelta(minutes=assumed_duration_minutes)
            except OverflowError as exc:
                raise InputError(
                    "Estimated event duration exceeds supported calendar bounds"
                ) from exc
        score, matched = _rank(event, wanted)
        candidates.append(_Candidate(event, start, end, score, matched, estimated))
    candidates.sort(key=lambda row: (row.start, row.event["id"]))
    best: tuple[_Candidate, ...] = ()
    best_score = 0.0
    best_tie = ()
    for count in range(1, min(max_events, len(candidates)) + 1):
        for subset in combinations(candidates, count):
            if not all(
                _compatible(left, right, transfer_buffer_minutes)
                for left, right in zip(subset, subset[1:])
            ):
                continue
            score = round(math.fsum(row.score for row in subset), 6)
            tie = tuple((row.start, row.event["id"]) for row in subset)
            if score > best_score or (
                score == best_score
                and (len(subset) > len(best) or (len(subset) == len(best) and tie < best_tie))
            ):
                best, best_score, best_tie = subset, score, tie
    chosen_ids = {row.event["id"] for row in best}
    for candidate in candidates:
        if candidate.event["id"] in chosen_ids:
            continue
        conflicts = [
            row.event["id"]
            for row in best
            if not _compatible(candidate, row, transfer_buffer_minutes)
        ]
        row = {
            "event": candidate.event,
            "reason_code": "schedule_conflict"
            if conflicts
            else "event_cap"
            if len(best) >= max_events
            else "lower_score",
        }
        if conflicts:
            row["conflicts_with"] = conflicts
        not_selected.append(row)
    selected = [
        {
            "event": row.event,
            "score": row.score,
            "matched_interests": row.matched,
            "duration_estimated": row.estimated,
            "effective_ends_at": row.end.isoformat(),
        }
        for row in best
    ]
    conditional = any(row.estimated for row in best)
    if needs_duration:
        warnings.append(
            f"Excluded {len(needs_duration)} event(s) without valid end times under strict duration policy."
        )
    if conditional:
        warnings.append(
            "This schedule is conditional on the explicitly assumed event durations; verify actual end times."
        )
    if any(row["reason_code"] == "invalid_start" for row in not_selected):
        warnings.append("Excluded event(s) with invalid or timezone-naive start timestamps.")
    if not selected:
        warnings.append("No eligible feasible events were selected from this candidate set.")
    assumptions = [
        f"Any transition involving physical or hybrid attendance allows {transfer_buffer_minutes} minutes; online-to-online allows 5 minutes.",
        "Transfer buffers are scheduling allowances, not traffic estimates, route guarantees or first-event commute checks.",
        "Best total ranking score within the supplied candidate set; scores add 20 per matching category interest or 5 per title/description interest to the upstream connection signal (0-100). Scores are not probabilities.",
        "Equal scores prefer more events, then the earliest chronological start and lexical event ID.",
        "Registration, admission, availability and listed-free claims require checking the event links.",
    ]
    if duration_policy == "estimate":
        assumptions.append(
            f"Missing or invalid end times use the explicitly requested {assumed_duration_minutes}-minute duration."
        )
    return {
        "selected": selected,
        "not_selected": not_selected,
        "needs_duration": needs_duration,
        "warnings": warnings,
        "assumptions": assumptions,
        "candidate_count": len(unique),
        "conditional_on_assumptions": conditional,
        "total_score": best_score,
    }
