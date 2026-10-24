"""Unit tests for smart context truncator."""

import pytest
from linter.truncator import truncate_context, balance_markdown_code_blocks
from linter.models import TruncationPolicy


def test_text_within_budget_untouched():
    text = "Short prompt within budget."
    res = truncate_context(text, max_tokens=100)
    assert res.truncated is False
    assert res.content == text
    assert res.characters_removed == 0


def test_head_truncation():
    text = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n" * 20
    res = truncate_context(text, max_characters=100, policy=TruncationPolicy.HEAD)
    assert res.truncated is True
    assert "Truncated" in res.content
    assert res.content.startswith("Line 1")


def test_tail_truncation():
    text = "Start Line\n" + ("Filler\n" * 30) + "End Line Final"
    res = truncate_context(text, max_characters=120, policy=TruncationPolicy.TAIL)
    assert res.truncated is True
    assert "Truncated" in res.content
    assert "End Line Final" in res.content


def test_sandwich_truncation():
    head = "System: Keep this important rule.\n"
    filler = "History message filler\n" * 50
    tail = "\nUser: Final urgent question."
    text = head + filler + tail

    res = truncate_context(text, max_characters=150, policy=TruncationPolicy.SANDWICH)
    assert res.truncated is True
    assert "System: Keep this" in res.content
    assert "Final urgent question." in res.content
    assert "Truncated" in res.content


def test_markdown_fence_balancing():
    unclosed = "Here is some code:\n```python\nprint(1)"
    balanced = balance_markdown_code_blocks(unclosed)
    assert balanced.endswith("```\n")
