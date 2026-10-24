"""Turn a digital lab PDF into rows.

The built-in reader drops identifier lines, then reads the demo table layout.
Model extraction is handled separately and sends the PDF text as printed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from app.corpus import BAIT

EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")
PHONE_RE = re.compile(r"\b\d{5}\s\d{5}\b")
RECORD_RE = re.compile(r"\b[A-Z]{2,10}-\d{3,}\b")
NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$")
RANGE_RE = re.compile(
    r"^([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*[-–]\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))$"
)
LT_RE = re.compile(r"^<\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))$")
GT_RE = re.compile(r"^>\s*([+-]?(?:\d+(?:\.\d+)?|\.\d+))$")

LABELS = {
    "patient name": "name",
    "phone": "phone",
    "email": "email",
    "record id": "record_id",
}

ALIASES = {
    "hb": "hemoglobin",
    "hgb": "hemoglobin",
    "haemoglobin": "hemoglobin",
    "hemoglobin": "hemoglobin",
    "wbc": "white blood cell count",
    "white blood cell count": "white blood cell count",
    "platelet count": "platelet count",
    "platelets": "platelet count",
    "ldl": "ldl cholesterol",
    "ldl cholesterol": "ldl cholesterol",
    "hdl": "hdl cholesterol",
    "hdl cholesterol": "hdl cholesterol",
    "triglycerides": "triglycerides",
    "fasting glucose": "fasting glucose",
    "glucose fasting": "fasting glucose",
}


class ParseError(ValueError):
    """The PDF text had no usable results table."""


@dataclass(frozen=True)
class LabRow:
    display_name: str
    analyte: str
    value: float | None
    value_text: str
    unit: str
    ref_low: float | None
    ref_high: float | None
    ref_text: str
    flag: str


@dataclass(frozen=True)
class Extraction:
    collected_on: str
    panel_name: str
    removed: tuple[str, ...]
    rows: tuple[LabRow, ...]
    redacted_text: str
    sent_provider: str = ""


def canonical_analyte(name: str) -> str:
    key = " ".join(name.strip().lower().replace("_", " ").replace("-", " ").split())
    compact = key.replace(" ", "")
    if compact in {"hba1c", "a1c"}:
        return "hba1c"
    return ALIASES.get(key, key)


def parse_ref(text: str) -> tuple[float | None, float | None]:
    cleaned = " ".join(text.strip().split())
    match = RANGE_RE.fullmatch(cleaned)
    if match:
        return float(match.group(1)), float(match.group(2))
    match = LT_RE.fullmatch(cleaned)
    if match:
        return None, float(match.group(1))
    match = GT_RE.fullmatch(cleaned)
    if match:
        return float(match.group(1)), None
    return None, None


def classify(value: float | None, low: float | None, high: float | None) -> str:
    if value is None or (low is None and high is None):
        return "unknown"
    if low is not None and value < low:
        return "below"
    if high is not None and value > high:
        return "above"
    return "within"


def parse_value(text: str) -> float | None:
    cleaned = text.strip()
    if NUMBER_RE.fullmatch(cleaned):
        return float(cleaned)
    return None


def make_row(display_name: str, value_text: str, unit: str, ref_text: str) -> LabRow:
    value = parse_value(value_text)
    low, high = parse_ref(ref_text)
    return LabRow(
        display_name=display_name.strip(),
        analyte=canonical_analyte(display_name),
        value=value,
        value_text=value_text.strip(),
        unit=unit.strip(),
        ref_low=low,
        ref_high=high,
        ref_text=ref_text.strip(),
        flag=classify(value, low, high),
    )


def _bait_in(line: str) -> bool:
    lowered = line.lower()
    return any(str(value).lower() in lowered for value in BAIT.values())


def redact_text(text: str) -> tuple[str, tuple[str, ...]]:
    """Drop identifier lines. Collection date and the results table stay."""
    removed: list[str] = []
    kept: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            kept.append("")
            continue
        labeled = re.match(r"^([^:]{2,40}):\s*(.*)$", line)
        if labeled:
            label = labeled.group(1).strip().lower()
            if label in LABELS:
                removed.append(LABELS[label])
                continue
        if EMAIL_RE.search(line) or _bait_in(line):
            removed.append("identifier")
            continue
        kept.append(line)
    ordered: list[str] = []
    for item in removed:
        if item not in ordered:
            ordered.append(item)
    return "\n".join(kept), tuple(ordered)


def text_is_unsafe(text: str) -> bool:
    """True when a prompt or stored analyte still carries an identifier."""
    if EMAIL_RE.search(text) or PHONE_RE.search(text) or RECORD_RE.search(text):
        return True
    return _bait_in(text)


def pdf_text(path: Path) -> str:
    try:
        reader = PdfReader(str(path))
        parts = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise ParseError("That PDF could not be read.") from exc
    return "\n".join(parts)


def parse_redacted(text: str) -> tuple[str, str, tuple[LabRow, ...]]:
    collected = ""
    panel = ""
    rows: list[LabRow] = []
    in_results = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if lower.startswith("collected:"):
            collected = stripped.split(":", 1)[1].strip()
            continue
        if lower.startswith("panel:"):
            panel = stripped.split(":", 1)[1].strip()
            continue
        if stripped == "RESULTS":
            in_results = True
            continue
        if not in_results or "|" not in stripped:
            continue
        if lower.startswith("test |"):
            continue
        parts = [part.strip() for part in stripped.split("|")]
        if len(parts) != 5:
            continue
        name, value, unit, ref, _flag = parts
        if not name or not value:
            continue
        rows.append(make_row(name, value, unit, ref))
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", collected):
        raise ParseError("The report has no collection date in YYYY-MM-DD form.")
    if not rows:
        raise ParseError("The report has no results table.")
    return collected, panel or "Lab panel", tuple(rows)


def extract_pdf(path: Path) -> Extraction:
    redacted, removed = redact_text(pdf_text(path))
    collected, panel, rows = parse_redacted(redacted)
    return Extraction(
        collected_on=collected,
        panel_name=panel,
        removed=removed,
        rows=rows,
        redacted_text=redacted,
    )
