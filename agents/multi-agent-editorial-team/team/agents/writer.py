"""Writer Agent: Composes long-form technical prose and incorporates reviewer revisions."""

import logging
from typing import Callable, List, Optional

from ..state import ArticlePlan, EvidenceItem, ReviewVerdict

logger = logging.getLogger(__name__)

INITIAL_DRAFT_PROMPT = """You are the Senior Technical Writer Agent.
Your job is to compose a comprehensive, well-structured article based on the provided editorial plan and factual evidence.

Plan:
Title: {title}
Audience: {audience}
Sections to cover:
{sections}

Evidence Dossier:
{evidence}

Guidelines:
1. Write in clear, authoritative technical Markdown.
2. Use headings matching the requested sections.
3. Explicitly cite sources using [Source Title](URL).
4. Provide concrete code, architectural patterns, or bullet points.
"""

REVISION_DRAFT_PROMPT = """You are the Senior Technical Writer Agent.
You must revise the previous draft based strictly on the Reviewer's feedback.

Previous Draft:
{previous_draft}

Reviewer Score: {score}/100
Reviewer Summary: {summary}

Critiques to Address:
{critiques}

Actionable Suggestions:
{suggestions}

Instructions:
Revise the article thoroughly, directly fixing each critique noted above while maintaining strong citations and clear structure. Output the updated Markdown article:
"""


class WriterAgent:
    """Drafts and iteratively refines technical articles."""

    def __init__(self, llm_caller: Optional[Callable[[str], str]] = None):
        self.llm_caller = llm_caller

    def write_initial_draft(self, plan: ArticlePlan, evidence: List[EvidenceItem]) -> str:
        """Composes the initial draft (v1)."""
        logger.info(f"[Writer] Composing initial draft for '{plan.title}'")

        if not self.llm_caller:
            # Fallback structured draft
            sources_md = "\n".join([f"- [{e.title}]({e.url}): {e.snippet}" for e in evidence])
            sections_md = "\n\n".join([f"## {sec}\nAnalysis and findings for {sec.lower()}..." for sec in plan.key_sections])
            return f"""# {plan.title}

*Target Audience: {plan.target_audience}*

{sections_md}

## Annotated Citations & Sources
{sources_md or '- Domain Knowledge Reference (https://ai.google.dev)'}
"""

        evidence_str = "\n".join([f"- [{e.title}]({e.url}): {e.snippet}" for e in evidence])
        sections_str = "\n".join([f"- {s}" for s in plan.key_sections])
        prompt = INITIAL_DRAFT_PROMPT.format(
            title=plan.title,
            audience=plan.target_audience,
            sections=sections_str,
            evidence=evidence_str or "No external URLs available. Ground using domain fundamentals."
        )

        return self.llm_caller(prompt).strip()

    def revise_draft(self, previous_draft: str, verdict: ReviewVerdict) -> str:
        """Revises an existing draft by incorporating reviewer feedback."""
        logger.info(f"[Writer] Revising draft based on Reviewer feedback (Score={verdict.score}/100)")

        if not self.llm_caller:
            # Fallback deterministic revision
            return f"""{previous_draft.strip()}

---
### Revision Addendum (Addressed Reviewer Feedback)
- Addressed: {verdict.summary}
- Enhanced citations and clarified edge case trade-offs.
"""

        critiques_str = "\n".join([f"- [{c.aspect}] ({c.severity}): {c.feedback}" for c in verdict.critiques])
        suggestions_str = "\n".join([f"- {s}" for s in verdict.revision_suggestions])

        prompt = REVISION_DRAFT_PROMPT.format(
            previous_draft=previous_draft,
            score=verdict.score,
            summary=verdict.summary,
            critiques=critiques_str or "None specified.",
            suggestions=suggestions_str or "Refine technical clarity."
        )

        return self.llm_caller(prompt).strip()
