"""Fact sheet built only from stored lab rows, plus the prompt a model may see."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from app.extract import parse_ref, text_is_unsafe


class PromptUnsafe(ValueError):
    """The fact sheet still contains an identifier, so it cannot be prompted."""


@dataclass(frozen=True)
class StoredResult:
    collected_on: str
    display_name: str
    analyte: str
    value: float | None
    value_text: str
    unit: str
    ref_text: str
    flag: str


@dataclass(frozen=True)
class Change:
    display_name: str
    analyte: str
    unit: str
    previous_on: str
    previous_value: str
    latest_on: str
    latest_value: str
    delta: str | None
    note: str


@dataclass(frozen=True)
class Meter:
    display_name: str
    analyte: str
    collected_on: str
    value_text: str
    unit: str
    ref_text: str
    flag: str
    marker: float | None
    within_start: float
    within_end: float
    has_interval: bool
    delta: str | None
    previous_on: str
    previous_value: str
    note: str


@dataclass(frozen=True)
class Outside:
    display_name: str
    analyte: str
    collected_on: str
    value_text: str
    unit: str
    ref_text: str
    flag: str


def _num(value: float) -> str:
    rounded = round(float(value), 4)
    text = f"{rounded:.4f}".rstrip("0").rstrip(".")
    return text or "0"


def _delta(latest: float, previous: float) -> str:
    diff = round(latest - previous, 4)
    text = _num(diff)
    if diff > 0:
        return f"+{text}"
    return text


def changes_for(results: list[StoredResult]) -> list[Change]:
    grouped: dict[str, list[StoredResult]] = {}
    for result in results:
        grouped.setdefault(result.analyte, []).append(result)
    found: list[Change] = []
    for analyte, rows in grouped.items():
        numeric = [row for row in rows if row.value is not None]
        if len(numeric) < 2:
            continue
        previous, latest = numeric[-2], numeric[-1]
        if previous.unit != latest.unit:
            delta = None
            note = "Units differ, so no numeric change is shown."
        else:
            delta = _delta(latest.value or 0, previous.value or 0)
            note = ""
        found.append(
            Change(
                display_name=latest.display_name,
                analyte=analyte,
                unit=latest.unit,
                previous_on=previous.collected_on,
                previous_value=previous.value_text,
                latest_on=latest.collected_on,
                latest_value=latest.value_text,
                delta=delta,
                note=note,
            )
        )
    return found


def _pct(value: float, scale_min: float, scale_max: float) -> float:
    span = scale_max - scale_min
    if span <= 0:
        return 50.0
    return (value - scale_min) / span * 100.0


def _clamp_marker(percent: float) -> float:
    return round(max(2.0, min(98.0, percent)), 1)


def _meter_geometry(
    value: float | None, low: float | None, high: float | None
) -> tuple[float | None, float, float, bool]:
    """Place a value on a 0–100 track. The middle band is the printed interval."""
    if value is None or (low is None and high is None):
        return None, 0.0, 100.0, False
    if low is not None and high is not None:
        span_lo = min(low, value)
        span_hi = max(high, value)
        pad = (span_hi - span_lo) * 0.2 or 1.0
        scale_min = span_lo - pad
        scale_max = span_hi + pad
        within_start = _pct(low, scale_min, scale_max)
        within_end = _pct(high, scale_min, scale_max)
    elif high is not None:
        scale_min = 0.0 if min(value, high) >= 0 else min(value, high)
        scale_max = max(value, high)
        if scale_max <= scale_min:
            scale_max = scale_min + 1.0
        if _pct(high, scale_min, scale_max) > 82:
            scale_max = scale_min + (high - scale_min) / 0.78
        if value > high and _pct(value, scale_min, scale_max) > 90:
            scale_max = scale_min + (value - scale_min) / 0.9
        within_start = 0.0
        within_end = _pct(high, scale_min, scale_max)
    else:
        assert low is not None
        scale_min = 0.0 if min(value, low) >= 0 else min(value, low)
        scale_max = max(value, low)
        if scale_max <= scale_min:
            scale_max = scale_min + 1.0
        if _pct(low, scale_min, scale_max) > 78:
            scale_max = scale_min + (low - scale_min) / 0.62
        if value > low and _pct(value, scale_min, scale_max) > 90:
            scale_max = scale_min + (value - scale_min) / 0.9
        within_start = _pct(low, scale_min, scale_max)
        within_end = 100.0
    if scale_max <= scale_min:
        scale_max = scale_min + 1.0
    return (
        _clamp_marker(_pct(value, scale_min, scale_max)),
        round(within_start, 1),
        round(within_end, 1),
        True,
    )


def meters_for(results: list[StoredResult]) -> list[Meter]:
    """One meter per analyte, using the latest stored value and its printed interval."""
    latest: dict[str, StoredResult] = {}
    for result in results:
        latest[result.analyte] = result
    change_by = {item.analyte: item for item in changes_for(results)}
    meters: list[Meter] = []
    for result in latest.values():
        change = change_by.get(result.analyte)
        low, high = parse_ref(result.ref_text)
        marker, within_start, within_end, has_interval = _meter_geometry(result.value, low, high)
        meters.append(
            Meter(
                display_name=result.display_name,
                analyte=result.analyte,
                collected_on=result.collected_on,
                value_text=result.value_text,
                unit=result.unit,
                ref_text=result.ref_text,
                flag=result.flag,
                marker=marker,
                within_start=within_start,
                within_end=within_end,
                has_interval=has_interval,
                delta=change.delta if change else None,
                previous_on=change.previous_on if change else "",
                previous_value=change.previous_value if change else "",
                note=change.note if change else "",
            )
        )
    order = {"above": 0, "below": 1, "within": 2, "unknown": 3}
    return sorted(meters, key=lambda item: (order.get(item.flag, 9), item.display_name.lower()))


def outside_latest(results: list[StoredResult]) -> list[Outside]:
    latest: dict[str, StoredResult] = {}
    for result in results:
        latest[result.analyte] = result
    found: list[Outside] = []
    for result in latest.values():
        if result.flag not in {"below", "above"}:
            continue
        found.append(
            Outside(
                display_name=result.display_name,
                analyte=result.analyte,
                collected_on=result.collected_on,
                value_text=result.value_text,
                unit=result.unit,
                ref_text=result.ref_text,
                flag=result.flag,
            )
        )
    return sorted(found, key=lambda item: item.display_name.lower())


def fact_sheet(results: list[StoredResult]) -> dict:
    """JSON-ready sheet. Keys are the only fields a model is allowed to see."""
    ordered = sorted(results, key=lambda item: (item.collected_on, item.analyte))
    return {
        "results": [
            {
                "analyte": item.analyte,
                "collected_on": item.collected_on,
                "flag": item.flag,
                "reference_interval": item.ref_text,
                "unit": item.unit,
                "value": item.value_text,
            }
            for item in ordered
        ],
        "outside_supplied_interval": [
            {
                "analyte": item.analyte,
                "collected_on": item.collected_on,
                "flag": item.flag,
                "reference_interval": item.ref_text,
                "unit": item.unit,
                "value": item.value_text,
            }
            for item in outside_latest(results)
        ],
        "changes": [
            {
                "analyte": item.analyte,
                "delta": item.delta,
                "latest_on": item.latest_on,
                "latest_value": item.latest_value,
                "previous_on": item.previous_on,
                "previous_value": item.previous_value,
                "unit": item.unit,
            }
            for item in changes_for(results)
            if item.delta is not None
        ],
    }


PROMPT_RULES = (
    "Write a short paragraph in plain sentences about the lab-history fact sheet. "
    "Use only numbers that appear in the sheet. "
    "Do not return JSON, field names, or a copy of the sheet. "
    "Do not name a condition, suggest treatment, or add any identifier."
)


def fact_payload(results: list[StoredResult]) -> str:
    payload = json.dumps(fact_sheet(results), indent=2, sort_keys=True)
    if text_is_unsafe(payload):
        raise PromptUnsafe("Fact sheet still contains an identifier.")
    return payload


def build_prompt(results: list[StoredResult]) -> str:
    return f"{PROMPT_RULES}\n\nFACT_SHEET\n{fact_payload(results)}\n"


def fact_hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def summary_is_prose(reply: str) -> bool:
    """A summary is a paragraph. The raw fact-sheet JSON is not a summary."""
    text = reply.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    if not text or text[0] in "{[":
        return False
    if "outside_supplied_interval" in text or '"analyte"' in text:
        return False
    return True


def summary_is_grounded(reply: str, payload: str) -> bool:
    """A summary may restate the sheet. It may not add identifiers or new numbers."""
    text = reply.strip()
    if not summary_is_prose(text) or text_is_unsafe(text):
        return False
    for number in re.findall(r"\d+(?:\.\d+)?", text):
        if number not in payload:
            return False
    return True
