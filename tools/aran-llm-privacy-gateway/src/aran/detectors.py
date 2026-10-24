"""Rule-based detectors for Indian identifiers, validated with their official checksums.

Each detector returns Finding spans. Checksums (Verhoeff for Aadhaar, mod-36 for GSTIN,
Luhn for cards) keep false positives low: a random 12-digit number is not an Aadhaar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    start: int
    end: int
    type: str
    value: str
    source: str = "rule"  # "rule" or "llm"
    validated: bool = False  # True when a checksum/format check passed


# --- Checksums ---------------------------------------------------------------

_VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]
_VERHOEFF_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_valid(digits: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(ch)]]
    return c == 0


def verhoeff_check_digit(digits: str) -> str:
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[(i + 1) % 8][int(ch)]]
    return str(_VERHOEFF_INV[c])


_GST_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_check_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        v = _GST_CHARS.index(ch) * (2 if i % 2 else 1)
        total += v // 36 + v % 36
    return _GST_CHARS[(36 - total % 36) % 36]


def gstin_valid(gstin: str) -> bool:
    return gstin_check_char(gstin[:14]) == gstin[14]


def luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


# --- Patterns ----------------------------------------------------------------

# PAN 4th char encodes the holder type (P = individual, C = company, ...).
_PAN_HOLDER_TYPES = "ABCFGHLJPT"

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("GSTIN", re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")),
    ("PAN", re.compile(rf"\b[A-Z]{{3}}[{_PAN_HOLDER_TYPES}][A-Z]\d{{4}}[A-Z]\b")),
    ("AADHAAR", re.compile(r"(?<![\d-])[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}(?![\d-])")),
    ("CARD", re.compile(r"(?<!\d)(?:\d{4}[ -]?){3}\d{1,7}(?!\d)")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\b")),
    ("UPI", re.compile(r"\b[\w.-]{2,64}@[A-Za-z]{2,32}\b(?!\.)")),
    ("PHONE", re.compile(r"(?<![\d+])(?:\+91[ -]?|0)?[6-9]\d{4}[ -]?\d{5}(?!\d)")),
    ("IFSC", re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")),
]

# Values that only count as PII when a label sits right before them.
_CONTEXTUAL: list[tuple[str, re.Pattern[str]]] = [
    (
        "ACCOUNT_NUMBER",
        re.compile(r"(?i)\b(?:a/?c|account|acct)\.?\s*(?:no\.?|number|#)?\s*[:\-]?\s*(\d{9,18})\b"),
    ),
    (
        "DOB",
        re.compile(
            r"(?i)\b(?:dob|d\.o\.b\.?|date\s+of\s+birth|birth\s*date)\s*[:\-/]?\s*"
            r"(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{4}-\d{2}-\d{2})"
        ),
    ),
    ("PINCODE", re.compile(r"(?i)\b(?:pin\s*code|pincode|pin)\s*[:\-]?\s*([1-9]\d{2}\s?\d{3})\b")),
    # Labelled names/addresses: a safety net under the local model, which can miss
    # values split across OCR lines.
    (
        "PERSON",
        re.compile(
            r"(?im)\b(?:(?:patient|employee|applicant|customer|father'?s|mother'?s|spouse|nominee)"
            r"\s+name|account\s+holder|referred\s+by)\s*[:\-]\s*"
            r"(?:(?:dr|mr|mrs|ms|shri|smt|kum)\.?\s+)?"  # title stays visible: "Dr. <PERSON_2>"
            r"([A-Z][A-Za-z.' ]{2,60}?)(?=\s{2,}|\s*$)"
        ),
    ),
    # Address value plus one continuation line, as long as that line is not another "Label:".
    ("ADDRESS", re.compile(r"(?im)\baddress\s*[:\-]\s*([^\n]{4,}(?:\n(?![^\n]*:)[^\n]{4,})?)")),
    (
        "MEDICAL_ID",
        re.compile(
            r"(?i)\b(?:uhid|mrn|patient\s*id|ip\s*no\.?|op\s*no\.?|reg(?:istration)?\.?\s*no\.?)"
            r"\s*[:\-]?\s*([A-Z0-9][A-Z0-9/-]{3,20})\b"
        ),
    ),
]


def _validate(kind: str, value: str) -> bool | None:
    """True = checksum passed, False = reject, None = no checksum for this type."""
    if kind == "AADHAAR":
        return verhoeff_valid(_digits(value))
    if kind == "GSTIN":
        return gstin_valid(value)
    if kind == "CARD":
        d = _digits(value)
        return 13 <= len(d) <= 19 and luhn_valid(d)
    if kind == "PAN":
        return True  # format already encodes the holder-type rule
    return None


# OCR can drop or swap a character, turning a PAN into something no format rule matches.
# For OCR'd text, mask any ID-shaped token (letters and digits mixed) as ID_NUMBER.
_ID_SHAPED = re.compile(r"\b(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{8,14}\b")
# Digit groups where OCR may have dropped a digit or read 0/1/5/8/2 as O/I/S/B/Z,
# e.g. "4821 573O 962". Kept only if at least 8 real digits remain.
_NUMBER_SHAPED = re.compile(r"(?<![\w,.])[0-9OISBZ]{3,5}(?:[ -][0-9OISBZ]{3,5}){1,3}(?![\w,.])|(?<![\w,.])[0-9OISBZ]{9,16}(?![\w,.])")


def detect(text: str, *, ocr: bool = False) -> list[Finding]:
    """Find PII spans. With ocr=True, fail closed: checksum failures and ID-shaped tokens
    are still masked, because a misread digit must not turn into a leak."""
    found: list[Finding] = []
    for kind, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            ok = _validate(kind, m.group(0))
            if ok is False:
                if ocr:
                    found.append(Finding(m.start(), m.end(), "ID_NUMBER", m.group(0), "ocr-guard"))
                continue
            found.append(Finding(m.start(), m.end(), kind, m.group(0), "rule", ok is True))
    for kind, pattern in _CONTEXTUAL:
        for m in pattern.finditer(text):
            found.append(Finding(m.start(1), m.end(1), kind, m.group(1), "rule", False))
    if ocr:
        for m in _ID_SHAPED.finditer(text):
            found.append(Finding(m.start(), m.end(), "ID_NUMBER", m.group(0), "ocr-guard"))
        for m in _NUMBER_SHAPED.finditer(text):
            if len(_digits(m.group(0))) >= 8:
                found.append(Finding(m.start(), m.end(), "ID_NUMBER", m.group(0), "ocr-guard"))
    return resolve_overlaps(found)


# Higher wins when spans overlap (a GSTIN contains a PAN; an email contains a UPI-like handle).
_PRIORITY = {
    "GSTIN": 90, "AADHAAR": 85, "CARD": 80, "PAN": 75, "EMAIL": 70, "ACCOUNT_NUMBER": 65,
    "MEDICAL_ID": 60, "DOB": 55, "UPI": 50, "PHONE": 45, "IFSC": 40, "PINCODE": 35,
    "PERSON": 30, "ADDRESS": 25, "ORG": 20, "ID_NUMBER": 10,
}


def resolve_overlaps(findings: list[Finding]) -> list[Finding]:
    ranked = sorted(
        findings,
        key=lambda f: (-int(f.validated), -_PRIORITY.get(f.type, 0), -(f.end - f.start)),
    )
    kept: list[Finding] = []
    for f in ranked:
        if all(f.end <= k.start or f.start >= k.end for k in kept):
            kept.append(f)
    return sorted(kept, key=lambda f: f.start)
