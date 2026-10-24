"""Parse a prompt into request text, context blocks and sentences, all with character offsets.

Offsets always refer to the original prompt so diagnostics can cite evidence and
patches can be applied as minimal edits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Blocks treated as supplied context (data) rather than the user's instructions.
CONTEXT_BLOCK = re.compile(
    r"```.*?(```|\Z)"  # fenced code (an unterminated fence runs to the end)
    r"|<pasted_content[^>]*>.*?</pasted_content[^>]*>"  # Claude Code pasted-text markers
    r"|<(document|documents|context|data|file|article|email|input|text)\b[^>]*>.*?</\2>",
    re.S | re.I,
)
_SENTENCE = re.compile(r"(?:[^\n.!?]|[.!?](?!\s|$))+[.!?]*", re.M)
_TEMPLATE_VAR = re.compile(r"\{\{\s*\w+\s*\}\}|\{\w+\}|\$\{\w+\}|<<\w+>>")


@dataclass
class Span:
    text: str
    start: int
    end: int


@dataclass
class PromptDoc:
    text: str
    sentences: list[Span] = field(default_factory=list)  # sentences of the request only
    blocks: list[Span] = field(default_factory=list)  # context blocks
    request: str = ""  # prompt with context blocks blanked out
    template_vars: list[Span] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(self.request.split())

    def in_block(self, pos: int) -> bool:
        return any(b.start <= pos < b.end for b in self.blocks)

    def find_all(self, pattern: re.Pattern[str], in_request: bool = True) -> list[Span]:
        """Regex matches with offsets; by default only outside context blocks."""
        out = []
        for m in pattern.finditer(self.text):
            if in_request and self.in_block(m.start()):
                continue
            out.append(Span(m.group(0), m.start(), m.end()))
        return out


def parse(text: str) -> PromptDoc:
    blocks = [Span(m.group(0), m.start(), m.end()) for m in CONTEXT_BLOCK.finditer(text)]
    chars = list(text)
    for b in blocks:  # blank out blocks, keeping offsets stable
        for i in range(b.start, b.end):
            if chars[i] != "\n":
                chars[i] = " "
    request = "".join(chars)

    sentences: list[Span] = []
    for m in _SENTENCE.finditer(request):
        raw = m.group(0)
        stripped = raw.strip()
        lead = len(raw) - len(raw.lstrip())
        # drop list markers so "- Keep it short." is the sentence "Keep it short."
        marker = re.match(r"^([-*•]|\d+[.)])\s+", stripped)
        if marker:
            lead += marker.end()
            stripped = stripped[marker.end():]
        if len(stripped) < 2 or not re.search(r"\w", stripped):
            continue
        start = m.start() + lead
        sentences.append(Span(stripped, start, start + len(stripped)))

    # re-join sentences split after abbreviations such as "e.g." or "i.e."
    merged: list[Span] = []
    for sp in sentences:
        if merged and re.search(r"\b(e\.g|i\.e|etc|vs|approx)\.$", merged[-1].text, re.I) and sp.start - merged[-1].end <= 2:
            prev = merged[-1]
            merged[-1] = Span(text[prev.start:sp.end], prev.start, sp.end)
        else:
            merged.append(sp)
    sentences = merged

    tvars = [Span(m.group(0), m.start(), m.end()) for m in _TEMPLATE_VAR.finditer(text)]
    return PromptDoc(text=text, sentences=sentences, blocks=blocks, request=request, template_vars=tvars)
