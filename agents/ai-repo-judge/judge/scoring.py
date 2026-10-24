"""Blend static checks and LLM ratings into dimension scores, an overall score, a verdict and a confidence.

Rules (also shown on the dashboard's Methodology page):
- Each dimension's static score is the weighted mean of its checks (pass=1, warn=0.5, fail=0, or a check's own score).
- The LLM contributes at most `llm_share` of a dimension (31% of the total overall); compliance is purely static.
- Any gating finding (committed key, out-of-scope change) makes the verdict "blocked", whatever the score.
- "ready" needs overall >= 70 and no high/critical static findings; otherwise "needs_changes".
- Attempts to manipulate AI judges cost 10 points overall.
"""

from __future__ import annotations

from dataclasses import dataclass

from judge.llm.review import LLMReview
from judge.models import SEVERITY_RANK, AnalyzerResult, Check, DimensionResult, Finding

READY_THRESHOLD = 70
MANIPULATION_PENALTY = 10
STATUS_VALUE = {"pass": 1.0, "warn": 0.5, "fail": 0.0}


@dataclass(frozen=True)
class Dim:
    key: str
    label: str
    weight: float
    llm_share: float
    purpose: str


RUBRIC = [
    Dim(
        "compliance",
        "Compliance",
        0.10,
        0.0,
        "Follows the repository's contribution rules: predicts whether the PR can be merged.",
    ),
    Dim(
        "security",
        "Security & Privacy",
        0.20,
        0.2,
        "Safe to merge and run: no secrets, no dangerous code, sound AI-specific safety.",
    ),
    Dim("quality", "Code Quality", 0.15, 0.3, "Maintainable, idiomatic, tested code."),
    Dim(
        "functionality",
        "Functionality & Reproducibility",
        0.20,
        0.4,
        "Does what it claims and installs and runs on someone else's machine.",
    ),
    Dim(
        "ai_native",
        "AI-Native",
        0.20,
        0.4,
        "How deeply and how well AI is engineered in, beyond a thin wrapper around one prompt.",
    ),
    Dim(
        "docs",
        "Docs & Developer Experience",
        0.10,
        0.3,
        "A newcomer can understand, set up and use it within five minutes.",
    ),
    Dim(
        "innovation",
        "Innovation & Impact",
        0.05,
        0.7,
        "Original and useful. Kept at a low weight because it is subjective.",
    ),
]
RUBRIC_BY_KEY = {d.key: d for d in RUBRIC}

# Which 1-5 LLM ratings feed each dimension, and how much each counts.
LLM_MAP: dict[str, dict[str, float]] = {
    "security": {"security_posture": 1.0},
    "quality": {"code_structure": 1.0},
    "functionality": {"functionality": 1.0, "_claims": 1.0},
    "ai_native": {"ai_depth": 0.5, "prompt_quality": 0.3, "ai_guardrails": 0.2},
    "docs": {"docs_clarity": 0.5, "example_realism": 0.5},
    "innovation": {"novelty": 0.5, "usefulness": 0.5},
}


def check_value(c: Check) -> float:
    return c.score if c.score is not None else STATUS_VALUE[c.status]


def static_score(checks: list[Check]) -> int | None:
    scored = [c for c in checks if c.status != "skip" and c.weight > 0]
    if not scored:
        return None
    total = sum(c.weight for c in scored)
    return round(100 * sum(c.weight * max(0.0, min(1.0, check_value(c))) for c in scored) / total)


def llm_score(dim: str, review: LLMReview | None) -> tuple[int | None, str | None]:
    if review is None or dim not in LLM_MAP:
        return None, None
    parts: list[tuple[float, float]] = []
    for key, w in LLM_MAP[dim].items():
        if key == "_claims":
            verified = [c for c in review.claims if c.status != "unverified"]
            if verified:  # unverified = not visible in the excerpts; it neither helps nor hurts
                val = {"implemented": 1.0, "partial": 0.5, "missing": 0.0}
                parts.append((w, 100 * sum(val[c.status] for c in verified) / len(verified)))
        elif key in review.scores:
            parts.append((w, (review.scores[key] - 1) * 25))
    if not parts:
        return None, None
    rationale = " ".join(review.rationales[k] for k in LLM_MAP[dim] if review.rationales.get(k))
    return round(sum(w * v for w, v in parts) / sum(w for w, _ in parts)), rationale or None


def score_dimensions(static: dict[str, AnalyzerResult], review: LLMReview | None) -> list[DimensionResult]:
    out = []
    for d in RUBRIC:
        res = static.get(d.key, AnalyzerResult())
        s = static_score(res.checks)
        llm, rationale = llm_score(d.key, review)
        if s is not None and llm is not None:
            score, share = round(s * (1 - d.llm_share) + llm * d.llm_share), d.llm_share
        elif s is not None:
            score, share = s, 0.0
        elif llm is not None:
            score, share = llm, 1.0
        else:
            score, share = None, 0.0
        findings = sorted(res.findings, key=lambda f: -SEVERITY_RANK[f.severity])
        out.append(
            DimensionResult(
                key=d.key,
                label=d.label,
                weight=d.weight,
                purpose=d.purpose,
                score=score,
                static_score=s,
                llm_score=llm,
                llm_share=share,
                llm_rationale=rationale,
                checks=res.checks,
                findings=findings,
            )
        )
    return out


def llm_findings(review: LLMReview | None) -> list[Finding]:
    if review is None:
        return []
    out = [
        Finding(
            dimension="security",
            severity=r.severity,
            title=r.title,
            detail=r.detail,
            file=r.file,
            line=r.line,
            source="llm",
        )
        for r in review.risks[:4]
    ]  # type: ignore[arg-type]
    if review.manipulation_attempt:
        out.append(
            Finding(
                dimension="security",
                severity="high",
                source="llm",
                title="LLM reviewer detected an attempt to manipulate AI judges",
                detail=review.manipulation_evidence[:300] or "See README and comments.",
                fix="Remove text addressed to graders or AI reviewers.",
            )
        )
    return out


def overall_score(dims: list[DimensionResult]) -> int:
    scored = [d for d in dims if d.score is not None]
    if not scored:
        return 0
    return round(sum(d.weight * d.score for d in scored) / sum(d.weight for d in scored))  # type: ignore[operator]


def confidence(dims: list[DimensionResult], llm_used: bool) -> int:
    """Share of the rubric backed by every evidence source it was designed to use."""
    total = got = 0.0
    for d in dims:
        rub = RUBRIC_BY_KEY[d.key]
        total += rub.weight
        if d.static_score is not None and (d.llm_score is not None or rub.llm_share == 0):
            got += rub.weight
        elif d.static_score is not None:
            got += rub.weight * (1 - rub.llm_share)
        elif d.llm_score is not None:
            got += rub.weight * rub.llm_share
    return round(100 * got / total) if total else 0


def verdict(dims: list[DimensionResult], overall: int) -> tuple[str, list[str]]:
    static = [f for d in dims for f in d.findings if f.source == "static"]
    gates = list(dict.fromkeys(f.title for f in static if f.gate))
    if gates:
        return "blocked", gates
    if overall >= READY_THRESHOLD and not any(SEVERITY_RANK[f.severity] >= 3 for f in static):
        return "ready", []
    return "needs_changes", []


def top_fixes(dims: list[DimensionResult], review: LLMReview | None, limit: int = 3) -> list[str]:
    fixes: list[str] = []
    for d in dims:
        fixes.extend(f.fix for f in d.findings if f.gate and f.fix)
    if review:
        fixes.extend(review.top_fixes)
    ranked = sorted(
        (
            (RUBRIC_BY_KEY[d.key].weight * c.weight * (2 if c.status == "fail" else 1), c.fix)
            for d in dims
            for c in d.checks
            if c.status in ("fail", "warn") and c.fix
        ),
        key=lambda t: -t[0],
    )
    fixes.extend(fix for _, fix in ranked if fix)
    return list(dict.fromkeys(fixes))[:limit]
