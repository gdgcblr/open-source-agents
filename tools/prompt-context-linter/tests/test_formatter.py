"""Unit tests for ContextFormatter."""

import pytest
from linter.context_formatter import ContextFormatter


def test_markdown_formatting():
    formatter = ContextFormatter(delimiter_style="markdown")
    res = formatter.build_context(
        system_role="Assistant",
        instructions=["Be polite", "Be fast"],
        user_query="What is 2+2?",
    )
    assert "# System Role\nAssistant" in res
    assert "## Instructions & Constraints" in res
    assert "- Be polite" in res
    assert "## User Request\nWhat is 2+2?" in res


def test_xml_formatting():
    formatter = ContextFormatter(delimiter_style="xml")
    res = formatter.build_context(
        system_role="Assistant",
        instructions=["Rule 1"],
        user_query="Hello",
        tools=[{"name": "calculator", "description": "Solves math"}],
    )
    assert "<system>\nAssistant\n</system>" in res
    assert "<instructions>\n- Rule 1\n</instructions>" in res
    assert "<tools>" in res
    assert "Tool: calculator" in res
    assert "<user_query>\nHello\n</user_query>" in res
