"""Deterministic scoring and the structured review report.

Scores, failures and the verdict are computed here from the pass/fail checks, so they
are repeatable. The LLM only contributes explanations and extra suggested fixes.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from .checks import CRITERIA
from .tools import _redact

READY_THRESHOLD = 85
MAX_EXTRA_FIXES = 5
MAX_FIX_CHARS = 300

# One concrete action per check, used even when the model adds nothing.
FIX_HINTS = {
    "manifest_present": "Add a dependency manifest (requirements.txt, package.json or pyproject.toml) listing every dependency.",
    "env_example_present": "Add a .env.example with placeholder values for every variable the project reads.",
    "deps_pinned": "Pin every dependency in requirements.txt to an exact version with ==.",
    "python_version_stated": "State the required Python version in the README prerequisites.",
    "run_command_documented": "Add the exact run command in a code block under a How to Run or Usage section.",
    "readme_present": "Create README.md from template/README.md.",
    "sections_present": "Add the missing README sections from template/README.md.",
    "no_placeholders": "Replace the leftover [Project Name]-style placeholders with real content.",
    "sections_not_thin": "Expand the thin README sections with concrete detail.",
    "commands_reference_real_files": "Fix the README commands so they only reference files that exist.",
    "links_ok": "Fix or remove the broken links in the README.",
    "no_secrets": "Remove committed secrets, .env files and virtualenvs, rotate any exposed key, and add them to .gitignore.",
    "gitignore_covers_secrets_and_venv": "Add .env, a virtualenv folder and __pycache__/ to .gitignore.",
    "no_risky_code": "Remove shell-execution, eval or exec calls, or document why they are safe.",
    "folder_name_ok": "Rename the folder to a lowercase kebab-case name that describes the project.",
    "pr_scope": "Revert changes outside your project folder; keep at most one agents/tools index row.",
}


class Failure(BaseModel):
    criterion: str = Field(description="reproducibility, documentation, security or scope")
    id: str = Field(description="Id of the failed check")
    reason: str = Field(description="Short reason the check failed")


class CriterionScores(BaseModel):
    reproducibility: Optional[int] = Field(default=None, ge=0, le=100)
    documentation: Optional[int] = Field(default=None, ge=0, le=100)
    security: Optional[int] = Field(default=None, ge=0, le=100)
    scope: Optional[int] = Field(default=None, ge=0, le=100)


class ReviewReport(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    criterion_scores: CriterionScores
    failures: List[Failure]
    suggested_fixes: List[str]
    verdict: Literal["ready", "needs_changes"]


def score_checks(checks: list) -> tuple:
    """Return (overall_score, per_criterion) from check results.

    A criterion's score is the percentage of its applicable checks that passed.
    Criteria with no applicable checks are left out; overall is the mean of the rest.
    """
    per = {}
    for criterion in CRITERIA:
        applicable = [c for c in checks if c["criterion"] == criterion and c["applicable"]]
        if applicable:
            per[criterion] = round(100 * sum(c["passed"] for c in applicable) / len(applicable))
    overall = round(sum(per.values()) / len(per)) if per else 0
    return overall, per


def verdict_for(overall: int, per: dict) -> str:
    """Ready needs a high overall score and a perfect security score."""
    if overall >= READY_THRESHOLD and per.get("security", 100) == 100:
        return "ready"
    return "needs_changes"


def _clean_fixes(extra) -> list:
    cleaned = []
    for fix in extra or []:
        if isinstance(fix, str) and fix.strip():
            cleaned.append(_redact(fix.strip())[:MAX_FIX_CHARS])
    return cleaned[:MAX_EXTRA_FIXES]


def build_report(checks: list, extra_fixes=None) -> ReviewReport:
    """Build the final report. `extra_fixes` are model-written suggestions, appended after the
    deterministic ones and cleaned (redacted, trimmed, capped, de-duplicated)."""
    overall, per = score_checks(checks)
    failed = [c for c in checks if c["applicable"] and not c["passed"]]
    fixes = [FIX_HINTS[c["id"]] for c in failed if c["id"] in FIX_HINTS]
    for fix in _clean_fixes(extra_fixes):
        if fix not in fixes:
            fixes.append(fix)
    return ReviewReport(
        overall_score=overall,
        criterion_scores=CriterionScores(**per),
        failures=[Failure(criterion=c["criterion"], id=c["id"], reason=c["reason"]) for c in failed],
        suggested_fixes=fixes,
        verdict=verdict_for(overall, per),
    )


def extra_fixes_from(llm_review) -> list:
    """Pull only the suggested_fixes strings out of the aggregator's output (dict or JSON text)."""
    import json

    if isinstance(llm_review, str):
        try:
            llm_review = json.loads(llm_review)
        except ValueError:
            return []
    if isinstance(llm_review, dict) and isinstance(llm_review.get("suggested_fixes"), list):
        return llm_review["suggested_fixes"]
    return []
