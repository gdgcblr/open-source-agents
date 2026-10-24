"""Unit tests for transcript and chat parser."""

import json
import pytest
from calculator.parser import parse_content


def test_parse_raw_text():
    raw = "Just a raw prompt string for a single turn query."
    b, fmt = parse_content(raw)
    assert fmt == "raw_prompt"
    assert b.prompt_tokens > 0
    assert b.completion_tokens == 0
    assert b.message_count == 1


def test_parse_chat_json():
    chat = [
        {"role": "user", "content": "Hello bot, what is Python?"},
        {"role": "assistant", "content": "Python is a high-level programming language."},
    ]
    b, fmt = parse_content(json.dumps(chat))
    assert fmt == "chat_json"
    assert b.prompt_tokens > 0
    assert b.completion_tokens > 0
    assert b.message_count == 2


def test_parse_jsonl_transcript():
    transcript = (
        '{"type": "USER_INPUT", "content": "Analyze logs"}\n'
        '{"type": "PLANNER_RESPONSE", "content": "Logs indicate zero failures"}\n'
    )
    b, fmt = parse_content(transcript)
    assert fmt == "jsonl_transcript"
    assert b.prompt_tokens > 0
    assert b.completion_tokens > 0
    assert b.message_count == 2
