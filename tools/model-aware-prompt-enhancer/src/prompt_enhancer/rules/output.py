"""Output-contract rules: format, schema, missing-value policy, audience."""

from __future__ import annotations

import re
from collections.abc import Iterator

from ..requirements import FORMAT, LENGTH
from . import Finding, RuleContext, add_line, ev, rule

_LONG_FORM = re.compile(r"\b(email|blog( post)?|post|article|essay|report|newsletter|announcement|letter|speech|documentation|docs|readme|press release|proposal|memo)\b", re.I)


@rule("PE301", "unspecified-output-format", "output-format", "info", tasks={"extraction", "research", "writing"},
      description="No output format or length is stated for a task where the shape of the answer matters.")
def unspecified_format(ctx: RuleContext) -> Iterator[Finding]:
    doc = ctx.doc
    if ctx.doc.find_all(FORMAT) or ctx.doc.find_all(LENGTH) or doc.word_count < 6:
        return
    if ctx.task_type == "writing" and not doc.find_all(_LONG_FORM):
        return  # a haiku or a tweet already implies its shape
    yield Finding(
        message=f"This {ctx.task_type} prompt does not say what shape the answer should take.",
        remediation="State the format and size you need (for example '5 bullet points', 'a Markdown table with columns X, Y', 'JSON with fields a, b').",
        severity="warning" if ctx.task_type == "extraction" else None,
        confidence=0.7,
        patches=[add_line(ctx, "Output format: {answer}", "Make the output contract explicit.",
                          question="What format and length should the answer have?")],
    )


_JSON = re.compile(r"\bjson\b", re.I)
_SCHEMA_HINT = re.compile(r"\b(fields?|keys?|schema|propert(y|ies)|columns?|attributes?)\b|\{\s*\"|\bwith\s+[\w\"'`]+\s*(,\s*[\w\"'`]+\s*)+(and|or)\s+[\w\"'`]+", re.I)


@rule("PE302", "json-without-schema", "output-format", "warning",
      description="JSON output is requested but the fields are never named.")
def json_without_schema(ctx: RuleContext) -> Iterator[Finding]:
    hits = ctx.doc.find_all(_JSON)
    if not hits or _SCHEMA_HINT.search(ctx.doc.text):
        return
    h = hits[0]
    yield Finding(
        message="JSON is requested but no field names or schema are given, so key names and nesting will vary between runs.",
        remediation="List the exact keys and types (or give one example object).",
        evidence=[ev(h.text, h.start, h.end)],
        confidence=0.75,
        patches=[add_line(ctx, "JSON fields: {answer}", "Pin down the JSON shape.",
                          question="Which keys (and types) should the JSON contain?")],
    )


_MISSING_POLICY = re.compile(r"\b(if (a|an|the|any|no)\b.{0,40}\b(missing|not (found|present|available|mentioned)|absent|unknown|empty)|null|n/?a\b|none\b|leave (it|them) (blank|empty)|omit)", re.I | re.S)


@rule("PE303", "no-missing-value-policy", "output-format", "info", tasks={"extraction"},
      description="Extraction prompt does not say what to do when a value is absent.")
def missing_value_policy(ctx: RuleContext) -> Iterator[Finding]:
    if _MISSING_POLICY.search(ctx.doc.request) or ctx.doc.word_count < 5:
        return
    yield Finding(
        message="Nothing says what to output when a requested value is not in the input, which invites guessed values.",
        remediation="Say how to mark missing values (for example null, 'N/A', or omit the item).",
        confidence=0.6,
        patches=[add_line(ctx, "If a value is missing: {answer}", "Prevent invented values.",
                          question="What should be output when a value is not present in the input?")],
    )


_AUDIENCE = re.compile(r"\b(audience|readers?|for (my|our|the|a|an) |tone|formal|informal|casual|friendly|professional|technical|non-technical|executive|beginners?|customers?|stakeholders?|leadership|team)\b", re.I)


@rule("PE304", "writing-missing-audience", "writing", "info", tasks={"writing"},
      description="Long-form writing request with no audience or tone.")
def writing_audience(ctx: RuleContext) -> Iterator[Finding]:
    doc = ctx.doc
    forms = doc.find_all(_LONG_FORM)
    if not forms or _AUDIENCE.search(doc.request):
        return
    f = forms[0]
    yield Finding(
        message=f"The {f.text} has no stated audience or tone, which strongly affects wording and length.",
        remediation="Name the reader and the tone (for example 'for non-technical customers, friendly tone').",
        evidence=[ev(f.text, f.start, f.end)],
        confidence=0.6,
        patches=[add_line(ctx, "Audience and tone: {answer}", "Anchor voice and level of detail.",
                          question="Who will read this, and what tone should it have?")],
    )
