"""Combine deterministic candidates with LLM verdicts under the safety policy.

SAFETY RULE: the LLM may only downgrade findings that are NOT high_confidence_format. A
known-format finding in a non-test path is always reported as `real`; the LLM can only add an
explanation. In test paths a known-format finding can be dismissed only at higher confidence.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from .guardrails import mask_text, safe_logger
from .llm import OllamaError, OllamaUnavailable
from .models import SEVERITIES, Candidate, Finding, TriageResult
from .remediation import short_remediation

log = safe_logger(__name__)

DISMISS_MIN_CONFIDENCE = 0.6
DISMISS_MIN_CONFIDENCE_KNOWN_FORMAT_IN_TESTS = 0.85


def _lower(sev: str) -> str:
    return SEVERITIES[max(0, SEVERITIES.index(sev) - 1)]


def decide(c: Candidate, result: TriageResult | None, error: str = "") -> Finding:
    rem = short_remediation(c.kind)
    sev = c.base_severity
    if result is None:
        return Finding(c, "unverified", 0.0, error or "Not triaged by an LLM (deterministic match only).",
                       rem, _lower(sev) if c.in_test_path else sev, "none")
    note = ""
    result = TriageResult(result.verdict, result.confidence, mask_text(result.reason),
                          mask_text(result.remediation), result.model, result.seconds)
    llm_rem = result.remediation or rem
    dismiss = result.verdict != "real"

    if dismiss and c.injection_suspected:
        note = (f"LLM suggested '{result.verdict}' but prompt-injection-like text sits next to this "
                "finding; dismissal ignored.")
        return Finding(c, "real", 1.0, result.reason, llm_rem, sev, "policy", note, result.seconds)

    if dismiss and c.high_confidence_format and not c.in_test_path:
        note = (f"LLM suggested '{result.verdict}' ({result.confidence:.2f}) but known-format secrets "
                "outside test paths cannot be dismissed by the LLM.")
        return Finding(c, "real", 1.0, result.reason, llm_rem, sev, "policy", note, result.seconds)

    if dismiss:
        need = (DISMISS_MIN_CONFIDENCE_KNOWN_FORMAT_IN_TESTS if c.high_confidence_format
                else DISMISS_MIN_CONFIDENCE)
        if result.confidence < need:
            note = (f"NEEDS HUMAN REVIEW: LLM suggested '{result.verdict}' but confidence "
                    f"{result.confidence:.2f} < {need}; kept as a finding.")
            return Finding(c, "uncertain", result.confidence, result.reason, llm_rem,
                           _lower(sev) if c.in_test_path else sev, "policy", note, result.seconds)
        return Finding(c, result.verdict, result.confidence, result.reason, llm_rem, "info", "llm", "",
                       result.seconds)

    return Finding(c, "real", result.confidence, result.reason, llm_rem, sev, "llm", "", result.seconds)


def triage_all(candidates: list[Candidate], triage_fn: Callable[[Candidate], TriageResult] | None,
               progress: Callable[[int, int], None] | None = None,
               warnings: list[str] | None = None, max_llm: int | None = None) -> list[Finding]:
    """FAIL CLOSED: every candidate yields exactly one Finding; any LLM problem (down, timeout,
    bad JSON, unexpected exception, over the cap) yields `unverified`, never a dismissal."""
    warnings = warnings if warnings is not None else []
    out: dict[int, Finding] = {}
    # Spend the LLM budget on generic findings first; known-format ones cannot be dismissed anyway.
    order = sorted(range(len(candidates)), key=lambda i: (candidates[i].high_confidence_format, i))
    budget = len(order) if max_llm is None else max_llm
    llm_down = False
    done = 0
    for n, i in enumerate(order):
        c = candidates[i]
        if triage_fn is None:
            out[i] = decide(c, None)
        elif llm_down:
            out[i] = decide(c, None, "LLM became unavailable during the run; kept as unverified.")
        elif n >= budget:
            out[i] = decide(c, None, "Not triaged: candidate cap reached; kept as unverified.")
        else:
            try:
                out[i] = decide(c, triage_fn(c))
            except OllamaUnavailable:
                llm_down = True
                warnings.append("Ollama became unavailable mid-run; remaining candidates are unverified.")
                out[i] = decide(c, None, "LLM became unavailable during the run; kept as unverified.")
            except OllamaError as e:
                log.warning("LLM triage failed for %s:%d (%s)", c.file, c.line, type(e).__name__)
                out[i] = decide(c, None, f"LLM triage failed ({type(e).__name__}); kept as unverified.")
            except Exception as e:  # noqa: BLE001 - fail closed on anything unexpected
                log.warning("unexpected triage error for %s:%d (%s)", c.file, c.line, type(e).__name__)
                out[i] = decide(c, None, f"Unexpected triage error ({type(e).__name__}); kept as unverified.")
        done += 1
        if progress:
            progress(done, len(candidates))
    if triage_fn is not None and len(candidates) > budget:
        warnings.append(f"Candidate cap: only {budget} of {len(candidates)} candidates were sent to the LLM; "
                        f"the other {len(candidates) - budget} are reported as unverified (raise --max-llm-candidates).")
    return [out[i] for i in range(len(candidates))]
