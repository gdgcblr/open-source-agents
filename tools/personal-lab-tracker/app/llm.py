"""Model calls for report extraction and fact-sheet summaries.

Local uses an OpenAI-compatible server such as Ollama. OpenAI uses the
official API. Extraction sends the PDF text the user uploaded. Summary
calls still receive only the fact sheet.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.extract import Extraction, ParseError, make_row, redact_text, text_is_unsafe

DEFAULT_LOCAL_BASE_URL = "http://127.0.0.1:11434/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"
LOCAL_MODELS = ("gemma3", "llama3.2", "qwen2.5")
OPENAI_MODELS = ("gpt-4.1-mini", "gpt-4o-mini", "gpt-4o")
PROVIDERS = ("local", "openai")
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$")

EXTRACTION_RULES = (
    "Extract laboratory results from the report text. "
    "The text may include a patient name, phone, email, address, or record id. "
    "Do not copy those into the JSON. "
    "Reply with JSON only, using keys collected_on, panel_name, and rows. "
    "collected_on must be YYYY-MM-DD. "
    "Each row has display_name, value, unit, and reference_interval. "
    "value is the printed result, without the unit. "
    "reference_interval is the interval printed on the report, or an empty string if none is printed. "
    "Include only laboratory tests."
)
MAX_REPORT_CHARS = 80_000


class LlmError(RuntimeError):
    """The configured model could not be used."""


@dataclass(frozen=True)
class LlmConfig:
    local_base_url: str
    openai_api_key: str
    extraction_provider: str
    extraction_model: str
    summary_provider: str
    summary_model: str

    @property
    def key_saved(self) -> bool:
        return bool(self.openai_api_key)

    def task(self, kind: str) -> tuple[str, str]:
        if kind == "extraction":
            return self.extraction_provider, self.extraction_model
        return self.summary_provider, self.summary_model

    @property
    def local_stays_on_machine(self) -> bool:
        host = (urlparse(self.local_base_url).hostname or "").lower()
        return host in {"127.0.0.1", "localhost", "::1"}


def config_from_row(row: dict | None) -> LlmConfig:
    data = row or {}
    return LlmConfig(
        local_base_url=str(data.get("local_base_url") or DEFAULT_LOCAL_BASE_URL),
        openai_api_key=str(data.get("openai_api_key") or ""),
        extraction_provider=str(data.get("extraction_provider") or "local"),
        extraction_model=str(data.get("extraction_model") or ""),
        summary_provider=str(data.get("summary_provider") or "local"),
        summary_model=str(data.get("summary_model") or ""),
    )


def valid_base_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and " " not in value
        and len(value) <= 200
    )


def valid_model(value: str) -> bool:
    return value == "" or MODEL_RE.fullmatch(value) is not None


def parse_settings_form(form, existing: LlmConfig) -> tuple[LlmConfig | None, str]:
    local_base_url = str(form.get("local_base_url") or "").strip() or DEFAULT_LOCAL_BASE_URL
    if not valid_base_url(local_base_url):
        return None, "The local base URL must start with http:// or https://."
    extraction_provider = str(form.get("extraction_provider") or "local")
    summary_provider = str(form.get("summary_provider") or "local")
    if extraction_provider not in PROVIDERS or summary_provider not in PROVIDERS:
        return None, "Each task must use Local or OpenAI."
    extraction_model = str(form.get("extraction_model") or "").strip()
    summary_model = str(form.get("summary_model") or "").strip()
    if not valid_model(extraction_model) or not valid_model(summary_model):
        return None, "Model names can use letters, numbers, and . _ : / -."
    submitted_key = str(form.get("openai_api_key") or "").strip()
    if form.get("clear_openai_key"):
        api_key = ""
    elif submitted_key:
        if len(submitted_key) > 300 or any(char.isspace() for char in submitted_key):
            return None, "That API key does not look usable."
        api_key = submitted_key
    else:
        api_key = existing.openai_api_key
    return (
        LlmConfig(
            local_base_url=local_base_url,
            openai_api_key=api_key,
            extraction_provider=extraction_provider,
            extraction_model=extraction_model,
            summary_provider=summary_provider,
            summary_model=summary_model,
        ),
        "",
    )


def endpoint(config: LlmConfig, kind: str) -> tuple[str, dict[str, str], str]:
    provider, model = config.task(kind)
    if not model:
        raise LlmError(f"Choose a model for {kind.replace('_', ' ')} in Settings.")
    if provider == "openai":
        if not config.openai_api_key:
            raise LlmError("Add an OpenAI API key in Settings, or switch this task to Local.")
        return (
            OPENAI_BASE_URL + "/chat/completions",
            {"Authorization": f"Bearer {config.openai_api_key}"},
            model,
        )
    if provider != "local":
        raise LlmError("Choose Local or OpenAI for this task.")
    if not valid_base_url(config.local_base_url):
        raise LlmError("The local base URL must start with http:// or https://.")
    return (
        config.local_base_url.rstrip("/") + "/chat/completions",
        {},
        model,
    )


def chat_complete(
    config: LlmConfig,
    kind: str,
    system: str,
    user_text: str,
    client: httpx.Client,
    *,
    allow_identifiers: bool = False,
) -> str:
    if not allow_identifiers and text_is_unsafe(user_text):
        raise LlmError("The prompt still contained an identifier, so it was not sent.")
    url, headers, model = endpoint(config, kind)
    try:
        response = client.post(
            url,
            headers=headers,
            json={
                "model": model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_text},
                ],
            },
        )
    except httpx.HTTPError as exc:
        raise LlmError("The model server could not be reached.") from exc
    if response.status_code >= 400:
        raise LlmError(f"The model request failed ({response.status_code}).")
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LlmError("The model returned an unexpected response.") from exc
    if not isinstance(content, str) or not content.strip():
        raise LlmError("The model returned an empty response.")
    return content


def _json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise LlmError("The model did not return JSON rows.")
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LlmError("The model did not return JSON rows.") from exc
    if not isinstance(parsed, dict):
        raise LlmError("The model did not return JSON rows.")
    return parsed


def rows_from_report_text(
    report_text: str,
    config: LlmConfig,
    client: httpx.Client,
) -> Extraction:
    """Send the PDF text to the extraction model the account selected."""
    text = report_text.strip()
    if not text:
        raise ParseError("This PDF has no selectable text. Scanned pages are not read yet.")
    if len(text) > MAX_REPORT_CHARS:
        raise ParseError("This PDF’s text is too long to send to a model.")
    removed = redact_text(report_text)[1]
    raw = chat_complete(
        config,
        "extraction",
        EXTRACTION_RULES,
        text,
        client,
        allow_identifiers=True,
    )
    parsed = _json_object(raw)
    collected = str(parsed.get("collected_on") or "").strip()
    panel = str(parsed.get("panel_name") or "").strip() or "Lab panel"
    if text_is_unsafe(panel):
        panel = "Lab panel"
    incoming = parsed.get("rows")
    if not isinstance(incoming, list) or not incoming:
        raise LlmError("The model did not return any lab rows.")
    rows = []
    for item in incoming:
        if not isinstance(item, dict):
            continue
        display_name = str(item.get("display_name") or "").strip()
        value = str(item.get("value") or "").strip()
        unit = str(item.get("unit") or "").strip()
        ref = str(item.get("reference_interval") or "").strip()
        blob = " ".join((display_name, value, unit, ref))
        if not display_name or not value or text_is_unsafe(blob):
            continue
        rows.append(make_row(display_name, value, unit, ref))
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", collected) or text_is_unsafe(collected):
        raise ParseError("The model did not return a collection date in YYYY-MM-DD form.")
    if not rows:
        raise LlmError("The model rows still looked like identifiers, so nothing was kept.")
    return Extraction(
        collected_on=collected,
        panel_name=panel,
        removed=removed,
        rows=tuple(rows),
        redacted_text="",
        sent_provider=config.extraction_provider,
    )
