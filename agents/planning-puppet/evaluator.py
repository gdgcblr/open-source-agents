"""
evaluator.py – Planning Puppet: LLM-as-a-Judge evaluator.

Passes the agent's event plan response to Gemini and asks it to score the
plan across four quality dimensions, returning a structured JSON result with
scores, feedback, and an overall pass/fail status.
"""

from __future__ import annotations

import json
import os
import re

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# ---------------------------------------------------------------------------
# Evaluator prompt
# ---------------------------------------------------------------------------

EVALUATOR_SYSTEM_PROMPT = """\
You are a strict but fair quality-assurance reviewer for AI-generated event
plans.  You will receive an event plan produced by an AI assistant and must
evaluate it across exactly four dimensions.

For each dimension, assign an integer score from 1 (very poor) to 5 (excellent)
and provide one short sentence of actionable feedback.

## Scoring Dimensions

1. **event_type_alignment** (1–5)
   Did the plan strictly address the nuances of the declared event type
   (wedding, birthday, or community event)?  Generic advice that could apply to
   any event should be penalised.

2. **budget_correctness** (1–5)
   Do the budget line items appear to sum correctly to the stated total?
   Is a contingency or safety buffer included?  Are the category percentages
   reasonable for the event type?

3. **timeline_feasibility** (1–5)
   Are the phased planning milestones realistic?  Do booking windows allow
   enough lead time?  Is the day-of schedule logical and achievable?

4. **tone_and_empathy** (1–5)
   Is the tone warm, celebratory, and reassuring while remaining structured
   and actionable?  Does it make the host feel supported rather than overwhelmed?

## Output Format
Respond ONLY with a valid JSON object matching this exact schema – no markdown,
no prose, no code fences:

{
  "scores": {
    "event_type_alignment": <int 1-5>,
    "budget_correctness": <int 1-5>,
    "timeline_feasibility": <int 1-5>,
    "tone_and_empathy": <int 1-5>
  },
  "feedback": {
    "event_type_alignment": "<one sentence>",
    "budget_correctness": "<one sentence>",
    "timeline_feasibility": "<one sentence>",
    "tone_and_empathy": "<one sentence>"
  },
  "overall_score": <float, average of the four scores, 1 decimal place>,
  "pass_fail": "<PASS if overall_score >= 3.5, otherwise FAIL>",
  "summary": "<2–3 sentence overall assessment of the plan quality>"
}
"""

EVALUATOR_USER_TEMPLATE = """\
Please evaluate the following AI-generated event plan:

---
{plan_text}
---
"""

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_plan(plan_text: str) -> dict:
    """Evaluate an event plan using an LLM-as-a-Judge approach.

    Sends the plan to Gemini and requests structured quality scores across
    four dimensions.  Returns a parsed dictionary with scores, per-dimension
    feedback, and an overall pass/fail verdict.

    Args:
        plan_text: The full text of the event plan produced by the agent.

    Returns:
        A dictionary with keys: scores, feedback, overall_score, pass_fail,
        and summary.  On error, returns a dict with an 'error' key.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {"error": "GEMINI_API_KEY is not set. Cannot run evaluator."}

    model_name = os.getenv("EVALUATOR_MODEL", os.getenv("MODEL_NAME", "gemini-3.8-flash"))

    client = genai.Client(api_key=api_key)

    user_message = EVALUATOR_USER_TEMPLATE.format(plan_text=plan_text)

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=user_message)],
                )
            ],
            config=types.GenerateContentConfig(
                system_instruction=EVALUATOR_SYSTEM_PROMPT,
                temperature=0.1,  # low temperature for consistent scoring
                response_mime_type="application/json",
            ),
        )

        raw_text = response.text.strip()

        # Strip markdown code fences if model wraps output despite instruction
        raw_text = re.sub(r"^`(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*`$", "", raw_text)

        result: dict = json.loads(raw_text)
        return result

    except json.JSONDecodeError as exc:
        return {"error": f"Failed to parse evaluator JSON: {exc}", "raw": raw_text}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Evaluator call failed: {exc}"}


def format_evaluation_report(evaluation: dict) -> str:
    """Format an evaluation result dictionary as a human-readable Rich string.

    Args:
        evaluation: The dict returned by evaluate_plan().

    Returns:
        A multi-line string suitable for printing to the terminal.
    """
    if "error" in evaluation:
        return f"[bold red]Evaluator Error:[/bold red] {evaluation['error']}"

    scores = evaluation.get("scores", {})
    feedback = evaluation.get("feedback", {})
    overall = evaluation.get("overall_score", 0)
    verdict = evaluation.get("pass_fail", "UNKNOWN")
    summary = evaluation.get("summary", "")

    verdict_colour = "green" if verdict == "PASS" else "red"
    lines: list[str] = [
        "",
        "[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]",
        "[bold cyan]   🎯  LLM-as-a-Judge Evaluation Report[/bold cyan]",
        "[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]",
    ]

    dimension_labels = {
        "event_type_alignment": "Event Type Alignment",
        "budget_correctness":   "Budget Correctness   ",
        "timeline_feasibility": "Timeline Feasibility ",
        "tone_and_empathy":     "Tone & Empathy       ",
    }

    for key, label in dimension_labels.items():
        score = scores.get(key, "N/A")
        fb = feedback.get(key, "")
        star_bar = "★" * int(score) + "☆" * (5 - int(score)) if isinstance(score, int) else ""
        lines.append(f"  [bold]{label}[/bold]  {star_bar}  [yellow]{score}/5[/yellow]")
        if fb:
            lines.append(f"    [dim]{fb}[/dim]")

    lines += [
        "",
        f"  [bold]Overall Score :[/bold] [yellow]{overall}/5.0[/yellow]",
        f"  [bold]Verdict       :[/bold] [{verdict_colour}]{verdict}[/{verdict_colour}]",
        "",
        f"  [italic]{summary}[/italic]",
        "[bold cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold cyan]",
        "",
    ]

    return "\n".join(lines)
