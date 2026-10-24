"""Anthropic Messages API tool rules."""

from __future__ import annotations

import re
from collections.abc import Iterable

from ..models import FORMAT_ANTHROPIC, Severity, ToolDef
from . import Issue, rule
from .general import PLACEHOLDER

ANTHROPIC_DEFINE = "Anthropic docs, 'Define tools' (tool definition parameters)"
ANTHROPIC_GUIDE = "Anthropic docs, 'Define tools' best practices"

_NAME = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
_SENTENCE_END = re.compile(r"[.!?](\s|$)")


@rule("A001", Severity.ERROR, "Tool name matches ^[a-zA-Z0-9_-]{1,128}$", ANTHROPIC_DEFINE,
      targets=[FORMAT_ANTHROPIC])
def anthropic_name(tool: ToolDef) -> Iterable[Issue]:
    if isinstance(tool.name, str) and tool.name and not _NAME.match(tool.name):
        yield Issue(tool.body_location + "/name",
                    f"tool name '{tool.name}' does not match ^[a-zA-Z0-9_-]{{1,128}}$",
                    "Replace dots, spaces, and other characters with '_' or '-'.")


@rule("A002", Severity.INFO, "Tool description has at least 3 sentences", ANTHROPIC_GUIDE,
      targets=[FORMAT_ANTHROPIC])
def anthropic_sentences(tool: ToolDef) -> Iterable[Issue]:
    d = tool.description
    if isinstance(d, str) and d.strip() and not PLACEHOLDER.match(d):
        sentences = len(_SENTENCE_END.findall(d.strip())) or 1
        if sentences < 3:
            yield Issue(tool.body_location + "/description",
                        f"description has {sentences} sentence(s); Anthropic recommends at least 3-4",
                        "Cover what the tool does, when to use it, what each parameter means, and caveats.")
