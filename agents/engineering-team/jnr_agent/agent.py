"""The Junior Engineer: implements the recorded design.

The only agent with write access to the shared workspace. Guardrail policy:
it cannot make design decisions. Any decision it tries to record is turned
into an issue for the Architect to sign off instead.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent
from google.genai import types

from shared_memory.engine import SYSTEM_PROMPT
from shared_memory.guardrails import GuardrailLog, make_callbacks
from shared_memory.protocol import JUNIOR, TEAM_CONTEXT, TOOL_RULE, live_model, model_for
from shared_memory.workspace import list_files, read_file, write_file, written_files

NAME = JUNIOR
TOOLS = [list_files, read_file, write_file]

PERSONA = TEAM_CONTEXT + """

ROLE: JUNIOR ENGINEER
- You implement exactly what the recorded design and decisions say.
- Write every source file with the write_file tool, using short relative paths.
  Use list_files and read_file to see what already exists before changing it.
- You do not make design decisions. If the design is unclear or wrong, open an issue
  for the Architect instead of deciding yourself.
- List every file you wrote as an artifact. When fixing review issues, put the ids of
  the issues you addressed in issues_resolved; the Senior Engineer verifies them."""


def policy(claims: dict, log: GuardrailLog, state: dict | None = None) -> dict:
    issues = claims.setdefault("issues_opened", [])

    for d in claims.pop("decisions", None) or []:
        text = d.get("decision", "") if isinstance(d, dict) else str(d)
        if text:
            issues.append({"description": "Junior proposed a design change (needs Architect "
                                          f"sign-off): {text}", "severity": "medium"})
            log.add(NAME, "decision-to-issue", text)

    # A file the junior names but never wrote with write_file is a claim, not an
    # artifact. Found in a live Gemini run: the model reported files it had not
    # written. In a cloned repository every file exists, so existence is not
    # enough; only files the agents wrote count.
    task_id = (state or {}).get("task_id", "")
    written = set(written_files(task_id)) if task_id else set()
    kept = []
    for a in claims.get("artifacts") or []:
        name = (a.get("name", "") if isinstance(a, dict) else str(a)).strip()
        if name in written:
            kept.append(a)
        elif name:
            issues.append({"description": f"Junior claimed {name} but never wrote it with write_file",
                           "severity": "high"})
            log.add(NAME, "unwritten-artifact", name)
    claims["artifacts"] = kept
    handoff = claims.get("handoff")
    if isinstance(handoff, dict):
        handoff["artifacts_mentioned"] = [n for n in handoff.get("artifacts_mentioned") or []
                                          if str(n).strip() in written]
    return claims


def build(model=None, log: GuardrailLog | None = None) -> LlmAgent:
    instruction = PERSONA + "\n\n" + SYSTEM_PROMPT + "\n" + TOOL_RULE
    return LlmAgent(
        name=NAME,
        description="Implements the recorded design as files in the shared workspace.",
        model=model or live_model(model_for(NAME)),
        instruction=lambda _ctx: instruction,
        include_contents="none",
        tools=list(TOOLS),
        generate_content_config=types.GenerateContentConfig(temperature=0.2),
        **make_callbacks(NAME, log or GuardrailLog(), policy=policy, may_write=True),
    )


root_agent = build()
