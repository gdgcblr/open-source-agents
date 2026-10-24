"""Use-cases. Orchestrates rules and an injected Provider. Knows nothing about files,
Gemini, ADK or the CLI: those live in adapters and interface layers."""
from typing import Callable, Optional

from .models import Category, RunInput, TestFailure, TriagedFailure, TriageResult, Verdict
from .ports import Provider
from .privacy import scan
from .rules import classify, scan_log_for_infra

DEFAULT_MAX_LLM_CALLS = 5


def log_context(test_name: str, lines: list[str], width: int = 3, limit: int = 40) -> list[str]:
    """Bounded log lines around mentions of the test name."""
    out: list[str] = []
    for i, line in enumerate(lines):
        if test_name in line:
            out += lines[max(0, i - width) : i + width + 1]
        if len(out) >= limit:
            break
    return out[:limit]


def apply_rules(run: RunInput) -> list[tuple[TestFailure, Optional[Verdict]]]:
    hits = scan_log_for_infra(run.log_lines)
    return [(f, classify(f, hits, run.history)) for f in run.failures]


def pii_counts(run: RunInput) -> dict[str, int]:
    """What the privacy layer found in the inputs (kinds and counts only)."""
    texts = [t for f in run.failures for t in (f.name, f.classname, f.message, f.details)]
    return scan(texts + run.log_lines)


def triage(
    run: RunInput,
    provider_factory: Callable[[], Provider],
    max_llm_calls: int = DEFAULT_MAX_LLM_CALLS,
) -> TriageResult:
    provider: Optional[Provider] = None
    calls = 0
    results: list[TriagedFailure] = []
    for failure, verdict in apply_rules(run):
        note = None
        if verdict is None:
            if calls >= max_llm_calls:
                verdict = Verdict(
                    category=Category.UNKNOWN, confidence=0.0, source="guardrail",
                    evidence=["no rule matched"], suggested_action="Inspect manually.",
                )
                note = f"LLM call cap ({max_llm_calls}) reached; left for manual review."
            else:
                provider = provider or provider_factory()  # created lazily: no key needed if rules suffice
                verdict = provider.classify(failure, log_context(failure.name, run.log_lines))
                calls += 1
        results.append(TriagedFailure(failure=failure, verdict=verdict, note=note))
    return TriageResult(results=results, total_tests=run.total_tests, pii_counts=pii_counts(run))
