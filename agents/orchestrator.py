"""The orchestrator: runs every reviewer, merges and ranks findings, picks a verdict."""
from __future__ import annotations

from .diff_parser import parse_diff
from .guardrails import check_diff, MAX_FILES
from .guardrails import remote_preflight
from .llm import LLMError, Provider
from .models import SEVERITY_RANK, Finding, ReviewResult
from .reviewers import LLMReviewer, QualityReviewer, SecurityReviewer, summarize


def decide_verdict(findings: list[Finding]) -> str:
    sevs = {f.severity for f in findings}
    if sevs & {"critical", "high"}:
        return "REQUEST_CHANGES"
    if "medium" in sevs:
        return "COMMENT"
    return "APPROVE"


def dedupe(findings: list[Finding]) -> list[Finding]:
    """Keep the most severe of any findings that share (file, line, title)."""
    best: dict[tuple, Finding] = {}
    for f in findings:
        k = f.key()
        if k not in best or SEVERITY_RANK[f.severity] < SEVERITY_RANK[best[k].severity]:
            best[k] = f
    return sorted(best.values(), key=lambda f: (SEVERITY_RANK[f.severity], f.file, f.line))


class ReviewOrchestrator:
    def __init__(self, provider: Provider, use_llm: bool = True):
        self.provider = provider
        self.use_llm = use_llm
        self.llm_reviewer = LLMReviewer(provider)
        self.reviewers = [SecurityReviewer(), QualityReviewer()]
        if use_llm:
            self.reviewers.append(self.llm_reviewer)

    def run(self, diff_text: str) -> ReviewResult:
        check_diff(diff_text)
        files = parse_diff(diff_text)
        if len(files) > MAX_FILES:
            raise ValueError("Diff contains too many files")
        if self.use_llm and self.provider.name not in ('mock', 'ollama'):
            remote_preflight(files)
        notes: list[str] = []
        findings: list[Finding] = []
        for reviewer in self.reviewers:
            try:
                findings.extend(reviewer.review(files))
            except Exception as e:  # one broken reviewer must not sink the whole review
                notes.append(f"{reviewer.name} reviewer failed")
        notes.extend(self.llm_reviewer.errors)

        findings = dedupe(findings)
        try:
            summary = summarize(self.provider, files, findings) if self.use_llm else (
                f"{len(files)} file(s) changed; {len(findings)} finding(s). Rules-only review; no model requests.")
        except LLMError as e:
            notes.append("Summary generation failed (provider error)")
            summary = f"{len(files)} file(s) changed, {len(findings)} finding(s)."

        return ReviewResult(
            summary=summary,
            verdict=decide_verdict(findings),
            findings=findings,
            stats={
                "files_changed": len(files),
                "lines_added": sum(len(f.added) for f in files),
                "provider": self.provider.name,
            },
            notes=notes,
        )
