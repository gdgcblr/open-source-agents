"""The Senior Engineer: reviews what was actually written.

Read-only access to the shared workspace (plus show_diff), and a write attempt is refused by
the guardrail even if a write tool were added. It may record a decision when a
review finding changes the design. Its claims that a fix is verified are still
only claims: the engine keeps those issues open with the claimant recorded.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.genai import types

from shared_memory.engine import SYSTEM_PROMPT
from shared_memory.guardrails import GuardrailLog, make_callbacks
from shared_memory.protocol import SENIOR, TEAM_CONTEXT, TOOL_RULE, live_model, model_for
from shared_memory.workspace import list_files, read_file, show_diff

NAME = SENIOR
TOOLS = [list_files, read_file, show_diff]

PERSONA = TEAM_CONTEXT + """

ROLE: SENIOR ENGINEER
- You review. You do not write or edit files.
- Use list_files and read_file to inspect the actual files, and show_diff to see exactly
  what changed in a cloned repository. Compare them with the recorded decisions and the objective.
- Open one issue per concrete defect, with a severity (low, medium or high).
- Only list an issue in issues_resolved after reading the file that fixes it.
- Record a decision only when a review finding changes the design, with its reason."""


def policy(claims: dict, log: GuardrailLog, state: dict | None = None) -> dict:
    """The senior writes nothing, so it cannot claim artifacts.

    Found in a live Gemini run: the senior listed the files it reviewed as its
    own artifacts ("todo.py v1"), which bumped versions it never changed.
    """
    for a in claims.pop("artifacts", None) or []:
        log.add(NAME, "artifact-dropped", a.get("name", "") if isinstance(a, dict) else str(a))
    handoff = claims.get("handoff")
    if isinstance(handoff, dict):
        for name in handoff.pop("artifacts_mentioned", None) or []:
            log.add(NAME, "artifact-dropped", str(name))
    return claims


def build(model=None, log: GuardrailLog | None = None) -> LlmAgent:
    instruction = PERSONA + "\n\n" + SYSTEM_PROMPT + "\n" + TOOL_RULE
    return LlmAgent(
        name=NAME,
        description="Reviews the files against the recorded design and opens issues.",
        model=model or live_model(model_for(NAME)),
        instruction=lambda _ctx: instruction,
        include_contents="none",
        tools=list(TOOLS),
        generate_content_config=types.GenerateContentConfig(temperature=0.2),
        **make_callbacks(NAME, log or GuardrailLog(), policy=policy, may_write=False),
    )


root_agent = build()
