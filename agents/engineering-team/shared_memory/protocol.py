"""What the team agrees on: who exists, the order of work, and the default model.

Agents import this; they never import each other.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

ARCHITECT, JUNIOR, SENIOR = "architect", "junior", "senior"
ROLES = (ARCHITECT, JUNIOR, SENIOR)
DEFAULT_MODEL = "gemini-3.8-flash"

# Appended after the JSON contract for agents that have tools. Without it, a
# live model told to "reply with ONE JSON object and nothing else" skips its
# tools and only claims it wrote the files.
TOOL_RULE = """
HOW TO WORK THIS TURN
1. First do the work with your tools: call them as many times as you need.
2. Only after every tool call is finished, send your final message: the JSON object.
Never claim a file in the JSON that you did not write or read with a tool this turn."""

TEAM_CONTEXT = (
    "You are one member of a three-person engineering team: the Architect, the Junior "
    "Engineer and the Senior Engineer. You never talk to each other directly. Each turn "
    "you receive only a briefing compiled from the team's shared memory, and your reply "
    "is checked before anything in it becomes part of that memory."
)


@dataclass(frozen=True)
class Step:
    role: str
    task: str


PIPELINE = (
    Step(ARCHITECT, "Architect: design the solution for the objective. Record the components, "
                    "interfaces, data model and implementation order as decisions with reasons."),
    Step(JUNIOR, "Junior engineer: implement the recorded design as source files with "
                 "write_file, following every recorded decision."),
    Step(SENIOR, "Senior engineer: review the implementation against the recorded design. "
                 "Read the files and open one issue per concrete defect."),
    Step(JUNIOR, "Junior engineer: fix the open review issues in the source files and list "
                 "the issue ids you addressed."),
    Step(SENIOR, "Senior engineer: final review. Read the files, confirm which issues are "
                 "actually fixed, and open issues for anything that remains."),
)

# Fixing a bug in a cloned repository. Same role order as PIPELINE, so the
# step -> agent mapping is identical; only the instructions differ.
FIX_PIPELINE = (
    Step(ARCHITECT, "Architect: investigate the bug in the cloned repository. Use list_files and "
                    "read_file to find the root cause. Record the root cause and the smallest fix "
                    "(which files and functions change) as decisions with reasons."),
    Step(JUNIOR, "Junior engineer: implement the fix the Architect recorded with write_file. Change "
                 "as little as possible, keep the existing style, and add or update a test that "
                 "fails without the fix."),
    Step(SENIOR, "Senior engineer: review the fix. Use show_diff to see exactly what changed, read "
                 "the surrounding code, and open one issue per concrete defect or missing test."),
    Step(JUNIOR, "Junior engineer: address the open review issues in the repository files and list "
                 "the issue ids you addressed."),
    Step(SENIOR, "Senior engineer: final review of the diff. Confirm which issues are actually "
                 "fixed and open issues for anything that remains."),
)
assert [s.role for s in FIX_PIPELINE] == [s.role for s in PIPELINE]

FIX_PREFIX = "Fix this bug in the repository cloned from "

DEMO_REQUEST = (
    "Build a small Python command-line to-do manager that stores tasks in a JSON file, "
    "with add, list and done commands."
)


def fix_objective(source: str, bug: str) -> str:
    return f"{FIX_PREFIX}{source}: {bug.strip()}"


def is_fix(objective: str) -> bool:
    return objective.startswith(FIX_PREFIX)


def model_for(role: str) -> str:
    """``ARCHITECT_MODEL`` / ``JUNIOR_MODEL`` / ``SENIOR_MODEL``, else the default."""
    return os.environ.get(f"{role.upper()}_MODEL") or DEFAULT_MODEL


def live_model(name: str):
    """A Gemini model that waits and retries on rate limits and transient errors.

    Free-tier keys allow only a few requests per minute per model, and one
    agent turn with tool calls makes several requests.
    """
    from google.adk.models.google_llm import Gemini
    from google.genai import types

    return Gemini(
        model=name,
        retry_options=types.HttpRetryOptions(
            attempts=8, initial_delay=10, max_delay=60, exp_base=2,
            http_status_codes=[429, 500, 502, 503, 504],
        ),
    )
