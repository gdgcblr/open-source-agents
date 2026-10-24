"""ADK agent definition. `root_agent` is what `adk web` / `adk run` discover."""

from __future__ import annotations

import os
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools import ToolContext
from google.genai import types

from . import duration
from .config import DEFAULT_MODEL, MAX_REVISIONS
from .prompts import SYSTEM_INSTRUCTION

# Session-scoped (not "temp:") so the count survives the JSON-retry turn; each
# request uses its own session.
_CHECKS_KEY = "speaking_time_checks"


def estimate_speaking_time(
    script_text: str, target_seconds: int, tool_context: ToolContext
) -> dict[str, Any]:
    """Measures how long the script takes to say and whether it fits the time slot.

    Args:
        script_text: All spoken text of the script, without headings.
        target_seconds: The speaker's time slot in seconds.

    Returns:
        Measured seconds, whether it fits, roughly how many words to add or cut,
        and how many revisions are left.
    """
    checks = int(tool_context.state.get(_CHECKS_KEY, 0)) + 1
    tool_context.state[_CHECKS_KEY] = checks

    seconds = duration.estimate_seconds(script_text)
    target = max(1, int(target_seconds))
    on_time = duration.fits_target(seconds, target)
    revisions_left = max(0, MAX_REVISIONS - (checks - 1))
    current_words = duration.word_count(script_text)
    goal_words = duration.target_words(target)
    change = goal_words - current_words
    if on_time:
        next_step = "Fits. Reply with the final JSON now."
    elif revisions_left == 0:
        next_step = "Revision limit reached. Stop revising and reply with the final JSON now."
    elif change > 0:
        next_step = (
            f"Too short: the script has {current_words} words and needs about {goal_words}. "
            f"Add the full {change} words, spread across every section: explain each point "
            "more, add transitions and a fuller opening and closing. Use only the notes; "
            "do not add new facts. Then check again."
        )
    else:
        next_step = (
            f"Too long: the script has {current_words} words and needs about {goal_words}. "
            f"Cut the full {-change} words, spread across every section, keeping every key "
            "point. Then check again."
        )
    return {
        "measured": duration.format_seconds(seconds),
        "measured_seconds": seconds,
        "target_seconds": target,
        "fits": on_time,
        "current_words": current_words,
        "target_words": goal_words,
        "word_change_needed": change,
        "revisions_left": revisions_left,
        "next_step": next_step,
    }


def _instruction(_: ReadonlyContext) -> str:
    # A callable instruction skips ADK's {placeholder} state injection, which
    # would otherwise misread the JSON key names in the prompt.
    return SYSTEM_INSTRUCTION


root_agent = LlmAgent(
    name="glasses_speaker_cue_agent",
    model=os.environ.get("MODEL_NAME", "").strip() or DEFAULT_MODEL,
    description="Turns talk notes into a timed script with short cues for smart glasses.",
    instruction=_instruction,
    tools=[estimate_speaking_time],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.7,
        http_options=types.HttpOptions(
            timeout=60_000,
            retry_options=types.HttpRetryOptions(
                attempts=3, initial_delay=2.0, http_status_codes=[429, 503]
            ),
        ),
    ),
)
