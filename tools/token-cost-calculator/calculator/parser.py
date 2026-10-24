"""Transcripts, Chat Histograms, and Prompt Parsers."""

import json
from typing import Any, Dict, List, Tuple
from .models import TokenBreakdown
from .tokenizer import count_tokens


def parse_content(raw_text: str, encoding: str = "cl100k_base") -> Tuple[TokenBreakdown, str]:
    """Inspects raw text, identifies the format (Chat JSON, JSONL Transcript, or Raw Prompt), and breaks down tokens.

    Args:
        raw_text: Source string content.
        encoding: Encoding to use for tokenization.

    Returns:
        Tuple of (TokenBreakdown, format_label).
    """
    stripped = raw_text.strip()
    if not stripped:
        return TokenBreakdown(), "empty"

    # 1. Try parsing as JSON Chat Array
    if stripped.startswith("[") and stripped.endswith("]"):
        try:
            data = json.loads(stripped)
            if isinstance(data, list) and all(isinstance(m, dict) and "role" in m for m in data):
                prompt_toks = 0
                comp_toks = 0
                total_chars = 0
                for msg in data:
                    role = msg.get("role", "user").lower()
                    content = str(msg.get("content", ""))
                    total_chars += len(content)
                    toks = count_tokens(content, encoding)
                    if role in ("assistant", "model", "bot"):
                        comp_toks += toks
                    else:
                        prompt_toks += toks

                return TokenBreakdown(
                    prompt_tokens=prompt_toks,
                    completion_tokens=comp_toks,
                    total_tokens=prompt_toks + comp_toks,
                    total_characters=total_chars,
                    message_count=len(data),
                ), "chat_json"
        except Exception:
            pass

    # 2. Try parsing as JSONL Transcript
    if "\n" in stripped:
        first_line = stripped.splitlines()[0].strip()
        if first_line.startswith("{") and first_line.endswith("}"):
            try:
                prompt_toks = 0
                comp_toks = 0
                total_chars = 0
                msg_count = 0
                for line in stripped.splitlines():
                    if not line.strip():
                        continue
                    step = json.loads(line)
                    msg_count += 1
                    content = str(step.get("content", step.get("text", "")))
                    total_chars += len(content)
                    toks = count_tokens(content, encoding)
                    step_type = str(step.get("type", step.get("source", ""))).upper()
                    if "PLANNER_RESPONSE" in step_type or "ASSISTANT" in step_type or "MODEL" in step_type:
                        comp_toks += toks
                    else:
                        prompt_toks += toks

                if msg_count > 0:
                    return TokenBreakdown(
                        prompt_tokens=prompt_toks,
                        completion_tokens=comp_toks,
                        total_tokens=prompt_toks + comp_toks,
                        total_characters=total_chars,
                        message_count=msg_count,
                    ), "jsonl_transcript"
            except Exception:
                pass

    # 3. Default: Raw Text / Markdown Prompt
    prompt_toks = count_tokens(stripped, encoding)
    return TokenBreakdown(
        prompt_tokens=prompt_toks,
        completion_tokens=0,
        total_tokens=prompt_toks,
        total_characters=len(stripped),
        message_count=1,
    ), "raw_prompt"
