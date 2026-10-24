"""The Architect: owns the design.

Read-only tools (to study an existing codebase before deciding). Its decisions
become binding shared memory for the other two agents. Guardrail policy: it cannot mark issues resolved, because verifying a
fix is the Senior Engineer's job.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.genai import types

from shared_memory.engine import SYSTEM_PROMPT
from shared_memory.guardrails import GuardrailLog, make_callbacks
from shared_memory.protocol import ARCHITECT, TEAM_CONTEXT, TOOL_RULE, live_model, model_for
from shared_memory.workspace import list_files, read_file

NAME = ARCHITECT
TOOLS = [list_files, read_file]

PERSONA = TEAM_CONTEXT + """

ROLE: ARCHITECT
- You own the design: components, interfaces, data model and the order of implementation.
- Record every design decision with its reason. Later turns treat decisions as binding.
- Keep the design small enough for one junior engineer to implement in a single turn.
- For a bug in an existing repository, read the relevant files first and record the
  root cause and the smallest fix as decisions.
- You may read files; you do not write them and you do not mark issues as resolved.
- Name the design document you produce as an artifact (for example design.md)."""


def policy(claims: dict, log: GuardrailLog, state: dict | None = None) -> dict:
    for ref in claims.pop("issues_resolved", None) or []:
        log.add(NAME, "resolution-dropped", str(ref))
    return claims


def build(model=None, log: GuardrailLog | None = None) -> LlmAgent:
    instruction = PERSONA + "\n\n" + SYSTEM_PROMPT + "\n" + TOOL_RULE
    return LlmAgent(
        name=NAME,
        description="Designs the solution and records binding decisions.",
        model=model or live_model(model_for(NAME)),
        # A callable instruction skips ADK's {placeholder} expansion, so the
        # braces in the JSON contract reach the model untouched.
        instruction=lambda _ctx: instruction,
        include_contents="none",
        tools=list(TOOLS),
        generate_content_config=types.GenerateContentConfig(temperature=0.2),
        **make_callbacks(NAME, log or GuardrailLog(), policy=policy, may_write=False),
    )


root_agent = build()
