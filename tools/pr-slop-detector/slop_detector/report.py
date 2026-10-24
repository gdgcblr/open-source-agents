"""Combine heuristic + LLM results into one score and render it for humans."""

from __future__ import annotations

import re

from .models import FinalReport, HeuristicReport, LlmVerdict, PullRequest, Verdict

# The LLM sees the actual code; heuristics are cheap but shallow. Weight accordingly...
LLM_WEIGHT = 0.65
# ...but only when the LLM backs its accusations with text that really occurs in the PR.
UNSUPPORTED_LLM_WEIGHT = 0.3
SEVERITIES = {"low", "medium", "high"}

BADGE = {
    Verdict.LOOKS_GOOD: "🟢 Looks good",
    Verdict.NEEDS_HUMAN_REVIEW: "🟡 Needs a closer human look",
    Verdict.LIKELY_SLOP: "🔴 Likely AI slop",
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def evidence_in_pr(pr: PullRequest, evidence: str | None) -> bool:
    """True if the snippet appears verbatim (modulo whitespace/case) in the PR text or diff.

    Bare file names don't count as evidence even though they appear in the PR.
    """
    snippet = _norm((evidence or "").strip("`'\" "))
    if len(snippet) < 4 or any(snippet == _norm(f.filename) for f in pr.files):
        return False
    haystack = _norm("\n".join([pr.title, pr.body, *pr.commit_messages, *(f.patch or "" for f in pr.files)]))
    return snippet in haystack


def real_findings(llm: LlmVerdict | None) -> list:
    """Small models sometimes emit a "no issues found" pseudo-finding without a real severity; drop those."""
    return [f for f in (llm.findings if llm else []) if f.severity.strip().lower() in SEVERITIES]


def llm_is_supported(pr: PullRequest, llm: LlmVerdict) -> bool:
    """A low score needs no evidence; a high one needs at least one verifiable quote."""
    findings = real_findings(llm)
    return not findings or llm.slop_score < 26 or any(evidence_in_pr(pr, f.evidence) for f in findings)


def verdict_for(score: int, threshold: int) -> Verdict:
    if score >= threshold:
        return Verdict.LIKELY_SLOP
    if score >= threshold * 0.45:
        return Verdict.NEEDS_HUMAN_REVIEW
    return Verdict.LOOKS_GOOD


def combine(
    pr: PullRequest, heur: HeuristicReport, llm: LlmVerdict | None, threshold: int, llm_error: str | None = None
) -> FinalReport:
    if llm is None:
        score = heur.score
    else:
        w = LLM_WEIGHT if llm_is_supported(pr, llm) else UNSUPPORTED_LLM_WEIGHT
        score = round(w * llm.slop_score + (1 - w) * heur.score)
    return FinalReport(
        pr=pr, heuristics=heur, llm=llm, llm_error=llm_error, score=score, verdict=verdict_for(score, threshold), threshold=threshold
    )


def to_markdown(r: FinalReport) -> str:
    pr = r.pr
    ref = f"[{pr.repo}#{pr.number}]({pr.url})" if pr.url else (f"{pr.repo}#{pr.number}" if pr.number else "local diff")
    lines = [
        f"## PR Slop Check: {BADGE[r.verdict]} (score {r.score}/100)",
        "",
        f"**{ref}** · {len(pr.files)} files · +{pr.additions} / -{pr.deletions}"
        + (f" · by @{pr.author.login}" if pr.author.login != "unknown" else ""),
        "",
    ]
    if r.llm:
        lines += [f"> {r.llm.summary}", ""]
    elif r.llm_error:
        lines += [f"> ⚠️ LLM review unavailable ({r.llm_error}); score is heuristics-only.", ""]
    else:
        lines += ["> Heuristics-only run (no LLM review).", ""]

    findings = real_findings(r.llm)
    if r.llm and not llm_is_supported(r.pr, r.llm):
        lines += [f"> ℹ️ None of the model's findings quote text found in the PR, so its score ({r.llm.slop_score}) was down-weighted.", ""]
    if findings:
        lines += ["### Findings", ""]
        for f in findings:
            where = f" (`{f.file}`)" if f.file else ""
            lines.append(f"- **[{f.severity}]** {f.claim}{where}")
            # Only show quotes that really occur in the PR; models (especially small ones) make them up.
            if evidence_in_pr(r.pr, f.evidence):
                lines.append(f"  > `{f.evidence.strip()[:200]}`")
        lines.append("")

    if r.llm and r.llm.strengths:
        lines += ["### Strengths", ""] + [f"- {s}" for s in r.llm.strengths] + [""]

    if r.llm and r.llm.questions_for_author:
        lines += ["### Questions for the author", ""] + [f"{i}. {q}" for i, q in enumerate(r.llm.questions_for_author, 1)] + [""]

    lines += [f"<details><summary>Heuristic signals (score {r.heuristics.score}/100, {len(r.heuristics.signals)} fired)</summary>", ""]
    if r.heuristics.signals:
        lines += ["| Signal | Weight | Evidence |", "| :--- | ---: | :--- |"]
        for s in r.heuristics.signals:
            ev = "<br>".join(e.replace("|", "\\|") for e in s.evidence)
            lines.append(f"| {s.title} | +{s.weight} | {ev} |")
    else:
        lines.append("No heuristic signals fired.")
    lines += [
        "",
        "</details>",
        "",
        f"<sub>Flag threshold: {r.threshold}. This is an automated triage aid, not a judgment of the contributor. "
        "AI-assisted work is welcome when it is correct, focused, and understood. A maintainer makes the final call.</sub>",
    ]
    return "\n".join(lines)
