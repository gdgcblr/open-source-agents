"""Local model calls through Ollama (default: Gemma). Nothing here talks to a cloud API."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import httpx

NER_TYPES = ("PERSON", "ADDRESS", "ORG")

_NER_PROMPT = """You find personal data in Indian documents. Return JSON only:
{{"entities": [{{"text": "<exact substring>", "type": "PERSON|ADDRESS|ORG"}}]}}

Rules:
- PERSON: full or partial names of people (applicant, patient, father/spouse, doctor, payee).
- ADDRESS: street/house/locality address lines of a person. Not just a city or state alone.
- ORG: companies, employers, banks, hospitals, labs, merchants.
- "text" must be copied exactly as it appears, character for character.
- Do not report ID numbers, phone numbers, emails, amounts or dates.
- If nothing is found return {{"entities": []}}.

Document:
<<<
{text}
>>>"""

_OCR_PROMPT = (
    "Transcribe ALL text in this document image exactly as printed, line by line, "
    "including every number, name, label and ID. Output plain text only, no commentary."
)


class LocalModelError(RuntimeError):
    pass


def _host() -> str:
    return os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")


def _model() -> str:
    return os.environ.get("ARAN_LOCAL_MODEL", "gemma4:12b")


def _chat(messages: list[dict], *, timeout: float = 300) -> str:
    # No `format: json`: some Ollama builds reject structured output for Gemma 4, so the
    # prompt asks for JSON and _parse_json extracts it.
    body = {
        "model": _model(),
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {"temperature": 0},
    }
    try:
        r = httpx.post(f"{_host()}/api/chat", json=body, timeout=timeout)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise LocalModelError(
            f"Local model {_model()!r} at {_host()} is unavailable ({e}). "
            "Start Ollama and run `ollama pull " + _model() + "`, or pass --no-llm."
        ) from e
    return r.json()["message"]["content"]


def _chunks(text: str, size: int = 3000) -> list[str]:
    lines, out, cur = text.splitlines(keepends=True), [], ""
    for line in lines:
        if len(cur) + len(line) > size and cur:
            out.append(cur)
            cur = ""
        cur += line
    if cur:
        out.append(cur)
    return out


def _parse_json(raw: str) -> dict:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {}


def find_entities(text: str) -> list[tuple[str, str]]:
    """Return (exact_text, type) pairs for names, addresses and organisations."""
    found: list[tuple[str, str]] = []
    for chunk in _chunks(text):
        raw = _chat([{"role": "user", "content": _NER_PROMPT.format(text=chunk)}])
        items = _parse_json(raw).get("entities", [])
        if not isinstance(items, list):
            continue
        for item in items:
            t, kind = str(item.get("text", "")).strip(), str(item.get("type", "")).upper()
            if kind in NER_TYPES and len(t) >= 3 and t in chunk:
                found.append((t, kind))
    return found


def transcribe_image(image: bytes | Path) -> str:
    data = image.read_bytes() if isinstance(image, Path) else image
    msg = {"role": "user", "content": _OCR_PROMPT, "images": [base64.b64encode(data).decode()]}
    return _chat([msg]).strip()
