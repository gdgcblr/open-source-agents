"""Deterministic guardrails around the model: the LLM proposes, code decides.

Input checks run before anything is sent to Gemini. Output checks run on the
model's draft before it is written to disk or shown on the glasses.
"""

from __future__ import annotations

import re

from .config import LANGUAGES, MAX_IMAGE_BYTES, MAX_MINUTES, MAX_NOTES_CHARS, MIN_MINUTES
from .deck import Deck


class InputError(ValueError):
    """The request is invalid; nothing was sent to the model."""


class BlockedError(ValueError):
    """A guardrail refused to send the request; nothing was sent to the model."""


_SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "Google API key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "OpenAI-style secret key": re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}"),
    "AWS access key ID": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "Private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Phone shapes only, separators within one line, so grouped figures such as
# "1 000 000 000" or lists of years are left alone.
_PHONE = re.compile(
    r"(?<![\w+])(?:"
    r"\+\d[\d ().-]{7,}\d"  # international, e.g. +91 98765 43210
    r"|\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}"  # North American, e.g. (555) 123-4567
    r"|[6-9]\d{4}[ -]?\d{5}"  # Indian mobile, e.g. 98765 43210
    r")(?!\w)"
)
_MIN_PHONE_DIGITS = 10
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")

_IMAGE_SIGNATURES: list[tuple[str, bytes, int]] = [
    ("image/png", b"\x89PNG\r\n\x1a\n", 0),
    ("image/jpeg", b"\xff\xd8\xff", 0),
    ("image/webp", b"WEBP", 8),
]

NOT_IN_NOTES = "⚠ Not in your notes — verify:"


def validate_notes(notes: str) -> str:
    notes = notes.strip()
    if not notes:
        raise InputError("Notes are empty. Write a few lines about your talk.")
    if len(notes) > MAX_NOTES_CHARS:
        raise InputError(
            f"Notes are {len(notes)} characters; the limit is {MAX_NOTES_CHARS}. "
            "Trim them to the points you want to make."
        )
    return notes


def validate_minutes(minutes: float) -> int:
    """Returns the target in whole seconds."""
    if not MIN_MINUTES <= minutes <= MAX_MINUTES:
        raise InputError(
            f"Target duration must be between {round(MIN_MINUTES * 60)} seconds "
            f"and {MAX_MINUTES:g} minutes."
        )
    return round(minutes * 60)


def validate_language(code: str) -> str:
    """Returns the language name for an allowed language code."""
    name = LANGUAGES.get(code.strip().lower())
    if name is None:
        raise InputError(f"Unsupported language '{code}'. Use one of: {', '.join(LANGUAGES)}.")
    return name


def validate_image(data: bytes) -> str:
    """Returns the MIME type, checked from the file signature, not the file name."""
    if len(data) > MAX_IMAGE_BYTES:
        raise InputError(f"Slide image is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB.")
    for mime, signature, offset in _IMAGE_SIGNATURES:
        if data[offset : offset + len(signature)] == signature:
            return mime
    raise InputError("Slide must be a PNG, JPEG or WebP image.")


def find_secrets(text: str) -> list[tuple[int, str]]:
    """(line number, kind) for every likely secret. Values are never returned."""
    found: list[tuple[int, str]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in _SECRET_PATTERNS.items():
            if pattern.search(line):
                found.append((line_no, kind))
    return found


def block_secrets(text: str) -> None:
    found = find_secrets(text)
    if found:
        where = "; ".join(f"line {line}: {kind}" for line, kind in found)
        raise BlockedError(
            f"Your notes look like they contain a secret ({where}). Nothing was sent. "
            "Remove it, and rotate the key if it is real."
        )


def redact_pii(text: str) -> tuple[str, dict[str, int]]:
    """Replaces emails and phone numbers; returns the new text and what was replaced."""
    text, emails = _EMAIL.subn("[EMAIL]", text)
    phones = 0

    def _phone(match: re.Match[str]) -> str:
        nonlocal phones
        if sum(ch.isdigit() for ch in match.group()) < _MIN_PHONE_DIGITS:
            return match.group()
        phones += 1
        return "[PHONE]"

    text = _PHONE.sub(_phone, text)
    return text, {"email": emails, "phone": phones}


def fence_notes(notes: str) -> str:
    """Stops notes from closing the <notes> block the prompt wraps them in."""
    return re.sub(r"</?\s*notes\s*>", "[notes tag removed]", notes, flags=re.IGNORECASE)


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUMBER.findall(text)}


def check_grounding(deck: Deck, notes: str, has_slide: bool = False) -> Deck:
    """Flags numbers the notes do not contain and Q&A answers the notes do not support.

    Code cannot read the slide, so with a slide attached, numbers missing from
    the notes are flagged as "check against your slide" rather than as
    invented, and the model's fromNotes claim decides the Q&A marking.
    """
    known = _numbers(notes)
    label = "number not in notes, check your slide" if has_slide else "number not in notes"
    cues = []
    for cue in deck.cues:
        unknown = sorted(_numbers(cue.text) - known)
        flags = [*cue.flags, *(f"{label}: {n}" for n in unknown)]
        cues.append(cue.model_copy(update={"flags": flags}))

    qa = []
    for item in deck.qa:
        answer_unknown = bool(_numbers(item.answer) - known) and not has_slide
        supported = item.fromNotes and not answer_unknown
        if supported or item.answer.startswith(NOT_IN_NOTES):
            qa.append(item)
        else:
            qa.append(item.model_copy(update={"answer": f"{NOT_IN_NOTES} {item.answer}"}))

    warnings = list(deck.warnings)
    flagged = sum(1 for c in cues if c.flags)
    if flagged:
        where = "your notes; check them against your slide" if has_slide else "your notes"
        warnings.append(f"{flagged} cue(s) mention numbers that are not in {where} (⚠).")
    return deck.model_copy(update={"cues": cues, "qa": qa, "warnings": warnings})
