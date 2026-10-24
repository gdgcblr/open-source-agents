"""README review with guardrails.

Order of guardrails, each one able to stop the call:
  1. Secret gate   - any secret finding (X1/X2) means nothing is sent.
  2. Minimal data  - only README text is sent, truncated to rules.max_ai_chars.
  3. Redaction     - anything that still looks like a secret is replaced with [REDACTED].
  4. Injection     - README is wrapped as untrusted data; suspicious phrases are flagged.
  5. Validation    - output must match the schema (each criterion once, scores 1-5);
                     one retry, then the result is marked invalid_output.
  6. Containment   - provider errors become an AIResult, never an exception, and the
                     result never changes the pass/fail outcome.
"""

from __future__ import annotations

import json
import re

from pydantic import ValidationError

from .. import secret_patterns
from ..context import ProjectContext
from ..models import AIResult, AIUsage, ReadmeReview, Report
from . import prompts
from .providers import ProviderError, ReviewProvider

SECRET_CHECK_IDS = {"X1", "X2"}
MAX_REASON_CHARS = 400
MAX_SUGGESTIONS = 3
MAX_TOP_FIXES = 5

_INJECTION_PATTERNS = (
    re.compile(r"\b(ignore|disregard|forget)\b.{0,30}\b(previous|prior|above|earlier|all|any|your)\b.{0,20}"
               r"\b(instructions?|prompts?|rules?)\b", re.IGNORECASE),
    re.compile(r"\b(give|assign|rate|score)\b.{0,40}\b(5/5|10/10|full marks|perfect score|maximum score|"
               r"highest score|all 5s)\b", re.IGNORECASE),
    re.compile(r"\byou are (now )?(an?|the) (ai|assistant|reviewer|model|grader)\b", re.IGNORECASE),
    re.compile(r"\bsystem prompt\b", re.IGNORECASE),
    re.compile(r"</?\s*(system|assistant|instructions?)\s*>", re.IGNORECASE),
)


class InvalidOutput(ValueError):
    pass


def injection_flags(text: str) -> list[str]:
    flags = []
    for number, line in enumerate(text.split("\n"), start=1):
        if any(p.search(line) for p in _INJECTION_PATTERNS):
            flags.append(f"README line {number} looks like an instruction to an AI reviewer; it was treated as data.")
    return flags


def parse_review(raw: str) -> ReadmeReview:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidOutput(f"not valid JSON ({exc.msg})") from exc
    try:
        review = ReadmeReview.model_validate(data)
    except ValidationError as exc:
        raise InvalidOutput(f"does not match the schema ({exc.error_count()} error(s))") from exc

    names = [c.criterion for c in review.criteria]
    expected = set(prompts.CRITERIA)
    if sorted(names) != sorted(expected):
        missing = expected - set(names)
        extra = [n for n in names if n not in expected or names.count(n) > 1]
        raise InvalidOutput(f"criteria must appear exactly once each (missing {sorted(missing)}, "
                            f"unexpected/duplicate {sorted(set(extra))})")

    order = list(prompts.CRITERIA)
    for c in review.criteria:
        c.reason = c.reason[:MAX_REASON_CHARS]
        c.suggestions = c.suggestions[:MAX_SUGGESTIONS]
    review.criteria.sort(key=lambda c: order.index(c.criterion))
    review.top_fixes = review.top_fixes[:MAX_TOP_FIXES]
    return review


def _has_secret_findings(report: Report) -> bool:
    return any(r.id in SECRET_CHECK_IDS and r.findings for r in report.checks)


def review_readme(ctx: ProjectContext, report: Report, provider: ReviewProvider) -> AIResult:
    base = dict(provider=provider.name, model=provider.model, prompt_version=prompts.PROMPT_VERSION)

    if _has_secret_findings(report):
        return AIResult(status="skipped", **base,
                        message="Possible secrets were found (X1/X2). Fix those first; nothing was sent to the model.")
    if ctx.readme is None:
        return AIResult(status="skipped", **base, message="No README to review.")

    text = "\n".join(ctx.readme.lines)
    truncated = len(text) > ctx.rules.max_ai_chars
    text = text[: ctx.rules.max_ai_chars]
    text, redactions = secret_patterns.redact(text)
    flags = injection_flags(text)

    usage = AIUsage()
    prompt = prompts.build_prompt(text, truncated=truncated)
    last_error = ""
    for attempt in (1, 2):
        usage.attempts = attempt
        attempt_prompt = prompt if attempt == 1 else (
            f"{prompt}\n\nYour previous response was rejected because it {last_error}. "
            "Return only JSON that matches the schema."
        )
        try:
            response = provider.generate(system=prompts.SYSTEM_INSTRUCTION, prompt=attempt_prompt,
                                         schema=prompts.RESPONSE_SCHEMA)
        except ProviderError as exc:
            return AIResult(status="error", **base, message=str(exc), usage=usage, flags=flags,
                            truncated=truncated, redactions=redactions)
        usage.prompt_tokens = (usage.prompt_tokens or 0) + (response.prompt_tokens or 0)
        usage.output_tokens = (usage.output_tokens or 0) + (response.output_tokens or 0)
        usage.latency_ms = (usage.latency_ms or 0) + (response.latency_ms or 0)
        try:
            review = parse_review(response.text)
        except InvalidOutput as exc:
            last_error = str(exc)
            continue
        return AIResult(status="ok", **base, review=review, usage=usage, flags=flags,
                        truncated=truncated, redactions=redactions)

    return AIResult(status="invalid_output", **base, message=f"Model output was rejected twice: {last_error}.",
                    usage=usage, flags=flags, truncated=truncated, redactions=redactions)
