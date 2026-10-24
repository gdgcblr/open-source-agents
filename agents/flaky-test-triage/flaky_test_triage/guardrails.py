"""Guardrails for the Flaky Test Triage agent.

Pure functions (easy to unit test) plus thin ADK callbacks at the bottom.

Layers:
  1. Input    : size limit, "is this a test log?" check, prompt-injection block,
                secret redaction BEFORE the text reaches the model.
  2. Tools    : argument type and size validation.
  3. Output   : re-redact secrets, enforce report format, no em dashes.
  4. Blocking : a blocked request short-circuits both agents with a clear message.
"""
from __future__ import annotations

import re
from typing import Optional

MAX_LOG_CHARS = 30_000
BLOCK_PREFIX = "BLOCKED:"

# ---------- secret redaction ----------
_SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("PRIVATE_KEY", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)),
    ("GOOGLE_API_KEY", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b")),
    ("GOOGLE_API_KEY", re.compile(r"\bAQ\.[0-9A-Za-z_\-]{20,}")),
    ("AWS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b")),
    ("BEARER_TOKEN", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}")),
    ("CREDENTIAL", re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key)\b(\s*[=:]\s*)(\"[^\"]+\"|'[^']+'|[^\s,;&]+)")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
]


def redact_secrets(text: str, skip: tuple = ()) -> tuple[str, list[str]]:
    """Replace secrets with [REDACTED:<TYPE>]. Returns (clean_text, types_found).

    skip lists labels to leave alone (for example EMAIL when showing code diffs).
    """
    found: list[str] = []
    for label, pat in _SECRET_PATTERNS:
        if label in skip:
            continue
        def _sub(m, label=label):
            found.append(label)
            if label == "CREDENTIAL":
                return f"{m.group(1)}{m.group(2)}[REDACTED:{label}]"
            return f"[REDACTED:{label}]"
        text = pat.sub(_sub, text)
    return text, sorted(set(found))


# ---------- input validation ----------
_INJECTION = re.compile(
    r"(ignore|disregard|forget)\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules)"
    r"|reveal\s+(your\s+)?(system\s+)?(prompt|instructions)"
    r"|(print|show|output)\s+(your\s+)?(api[_ -]?key|system prompt|\.env)"
    r"|you\s+are\s+now\s+(a|an|in)\b"
    r"|act\s+as\s+(a|an)\s+(?!qa|test)",
    re.IGNORECASE,
)
_FAILURE_HINT = re.compile(
    r"exception|error|fail|assert|traceback|timeout|timed out|expected|status code|"
    r"\b[45]\d\d\b|refused|unable to|not found|no such",
    re.IGNORECASE,
)


def validate_input(text: str) -> tuple[bool, str]:
    """Return (ok, reason). reason is user-facing when ok is False."""
    if not text or not text.strip():
        return False, "No input received. Please paste a failing test log."
    if _INJECTION.search(text):
        return False, ("The input contains instructions aimed at the assistant. "
                       "I only analyse test failure logs, so I ignored it.")
    if not _FAILURE_HINT.search(text):
        return False, ("This does not look like a test failure log. Paste the error "
                       "output, stack trace or console log of a failing test.")
    return True, ""


def truncate_log(text: str, limit: int = MAX_LOG_CHARS) -> tuple[str, bool]:
    """Keep head and tail of oversized logs, since errors sit at both ends."""
    if len(text) <= limit:
        return text, False
    half = limit // 2
    return text[:half] + "\n...[TRUNCATED BY GUARDRAIL]...\n" + text[-half:], True


def sanitize_input(text: str) -> tuple[Optional[str], str, list[str]]:
    """Full input pipeline. Returns (clean_text or None, message, redaction_types).

    clean_text is None when the request is blocked, and message explains why.
    """
    ok, reason = validate_input(text)
    if not ok:
        return None, reason, []
    clean, truncated = truncate_log(text)
    clean, found = redact_secrets(clean)
    notes = []
    if truncated:
        notes.append("log truncated")
    if found:
        notes.append("redacted: " + ", ".join(found))
    return clean, "; ".join(notes), found


# ---------- tool argument checks ----------
def check_tool_args(tool_name: str, args: dict) -> Optional[str]:
    """Return an error string if the arguments are unsafe or malformed."""
    if tool_name in ("parse_test_log", "classify_failure", "triage_log_text"):
        v = args.get("log_text")
        if not isinstance(v, str) or not v.strip():
            return "log_text must be a non-empty string"
        if len(v) > MAX_LOG_CHARS + 100:
            return "log_text is too large"
    elif tool_name == "check_flakiness_history":
        v = args.get("test_name")
        if not isinstance(v, str) or not v.strip() or len(v) > 300:
            return "test_name must be a short non-empty string"
        if re.search(r"[\\\n\r\x00]|\.\./", v):
            return "test_name contains illegal characters"
    elif tool_name in ("run_batch_triage", "suggest_fix_diff"):
        key = "folder" if tool_name == "run_batch_triage" else "source_path"
        v = args.get(key, "sample_batch" if key == "folder" else None)
        if not isinstance(v, str) or not v.strip() or len(v) > 300 or "\x00" in v:
            return f"{key} must be a short non-empty string"
        cat = args.get("category", "")
        if tool_name == "suggest_fix_diff" and (not isinstance(cat, str) or len(cat) > 60):
            return "category must be a short string"
    elif tool_name == "combine_signals":
        if not isinstance(args.get("classification"), dict) or not isinstance(args.get("history"), dict):
            return "classification and history must be objects"
    return None


# ---------- output checks ----------
def sanitize_output(text: str, require_verdict: bool = True) -> str:
    """Redact leaked secrets, strip em dashes, make sure the report is well formed."""
    text, _ = redact_secrets(text or "")
    text = text.replace("\u2014", " - ").replace("\u2013", "-")
    if require_verdict and "verdict" not in text.lower():
        text = ("_Note: the report format was unexpected. Treat this as unverified._\n\n"
                + text)
    return text


# ---------- ADK callbacks ----------
_TEXT_MIMES = ("text/", "application/json", "application/xml", "application/octet-stream",
               "application/x-log", "application/x-yaml")


def _content_text(content) -> str:
    """Text of a user message, including uploaded text files (arrive as inline_data)."""
    chunks = []
    for p in content.parts or []:
        if getattr(p, "text", None):
            chunks.append(p.text)
        blob = getattr(p, "inline_data", None)
        if blob is not None and getattr(blob, "data", None):
            mime = (getattr(blob, "mime_type", "") or "").lower()
            name = getattr(blob, "display_name", None) or "file"
            if not mime or mime.startswith(_TEXT_MIMES):
                raw = blob.data
                text = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
                chunks.append(f"[Uploaded file: {name}]\n{text}")
            else:
                chunks.append(f"[Unsupported upload: {mime or 'unknown type'}. Please upload a .log or .txt file.]")
    return "\n".join(chunks)


def _last_user_text(llm_request) -> str:
    for content in reversed(llm_request.contents or []):
        if content.role == "user":
            return _content_text(content)
    return ""


def _set_last_user_text(llm_request, new_text: str) -> None:
    """Replace the whole user message with sanitized text (drops raw file attachments)."""
    from google.genai import types
    for content in reversed(llm_request.contents or []):
        if content.role == "user":
            content.parts = [types.Part(text=new_text)]
            return


def _text_response(text: str):
    from google.adk.models import LlmResponse
    from google.genai import types
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))


def analyzer_before_model(callback_context, llm_request):
    """Input guardrail. Runs before every analyzer model call."""
    # Only guard the first call (the raw user message). Later calls carry tool results.
    last = (llm_request.contents or [None])[-1]
    is_first_call = last is not None and last.role == "user" and not any(
        getattr(p, "function_response", None) for p in last.parts or [])
    if not is_first_call:
        return None
    clean, msg, _ = sanitize_input(_last_user_text(llm_request))
    if clean is None:
        return _text_response(f"{BLOCK_PREFIX} {msg}")
    _set_last_user_text(llm_request, clean)
    callback_context.state["guardrail_notes"] = msg
    return None


def tool_guard(tool, args, tool_context):
    """Validate tool arguments. Returning a dict skips the real tool call."""
    err = check_tool_args(tool.name, args)
    if err:
        return {"error": f"Guardrail rejected tool call: {err}"}
    return None


def reporter_before_model(callback_context, llm_request):
    """If the analyzer blocked the request, relay the reason without calling the model."""
    analysis = str(callback_context.state.get("analysis", ""))
    if analysis.startswith(BLOCK_PREFIX):
        return _text_response(analysis[len(BLOCK_PREFIX):].strip())
    return None


def reporter_after_model(callback_context, llm_response):
    """Output guardrail on the final report."""
    content = getattr(llm_response, "content", None)
    if not content or not content.parts:
        return None
    changed = False
    for p in content.parts:
        if getattr(p, "text", None):
            cleaned = sanitize_output(p.text)
            if cleaned != p.text:
                p.text, changed = cleaned, True
    return llm_response if changed else None


# ---------- Batch Triage Studio callbacks (free-text requests, not raw logs) ----------
def validate_request(text: str) -> tuple[bool, str]:
    if not text or not text.strip():
        return False, "No input received. Ask me to triage a folder of logs or to suggest a fix."
    if _INJECTION.search(text):
        return False, ("The input contains instructions aimed at the assistant. "
                       "I only triage test failures, so I ignored it.")
    return True, ""


def studio_before_model(callback_context, llm_request):
    """Input guardrail for the studio agent. Guards the first call of each turn only."""
    last = (llm_request.contents or [None])[-1]
    is_user_turn = last is not None and last.role == "user" and not any(
        getattr(p, "function_response", None) for p in last.parts or [])
    if not is_user_turn:
        return None
    text = _last_user_text(llm_request)
    ok, reason = validate_request(text)
    if not ok:
        return _text_response(reason)
    clean, _ = redact_secrets(truncate_log(text)[0])
    _set_last_user_text(llm_request, clean)
    return None


def studio_after_model(callback_context, llm_response):
    """Output guardrail for the studio agent: no leaked secrets, no em dashes."""
    content = getattr(llm_response, "content", None)
    if not content or not content.parts:
        return None
    changed = False
    for p in content.parts:
        if getattr(p, "text", None):
            cleaned = sanitize_output(p.text, require_verdict=False)
            if cleaned != p.text:
                p.text, changed = cleaned, True
    return llm_response if changed else None
