"""Last step of the review team: builds the authoritative JSON report in plain code (no LLM)."""

from google.adk.agents import BaseAgent
from google.adk.events import Event, EventActions
from google.genai import types

from .analysis.checks import CRITERIA
from .analysis.scoring import build_report, extra_fixes_from

# State written during a review. Cleared at the start of every run so a follow-up question
# (for example a misspelled folder) can never reprint the previous review's results.
RESET_STATE = {
    **{f"checks_{criterion}": [] for criterion in CRITERIA},
    **{f"{criterion}_review": "" for criterion in CRITERIA},
    "llm_review": "",
    "review_project": "",
    "review_error": "",
    "final_review": {},
}

NO_REVIEW_MESSAGE = "No review was produced. Name a folder to review, for example: Review template"


class ReportFinalizer(BaseAgent):
    """Scores from the saved deterministic checks; keeps only the aggregator's extra fixes.

    The aggregator's own JSON may disagree with the checks, so this agent's report is the
    one to trust: its score, failures and verdict always come from the checks.
    """

    async def _run_async_impl(self, ctx):
        state = ctx.session.state
        checks = [c for criterion in CRITERIA for c in state.get(f"checks_{criterion}", [])]
        if checks:
            report = build_report(checks, extra_fixes_from(state.get("llm_review")))
            text = report.model_dump_json(indent=2)
            delta = {"final_review": report.model_dump()}
        else:
            text, delta = state.get("review_error") or NO_REVIEW_MESSAGE, {}
        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            content=types.Content(role="model", parts=[types.Part(text=text)]),
            actions=EventActions(state_delta=delta),
        )


class ReviewReset(BaseAgent):
    """First step of the team: clears the previous review's state (no model call, no output)."""

    async def _run_async_impl(self, ctx):
        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            actions=EventActions(state_delta=dict(RESET_STATE)),
        )
