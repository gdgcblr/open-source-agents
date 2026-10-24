"""Root ADK agent for Android UI automation.

Run it with ``adk run src`` / ``adk web`` from the project root, or one-shot
with ``python -m src "Open Brave and search for youtube.com"``.
"""

import argparse
import asyncio
import sys
from typing import List, Optional

from google.adk.agents.llm_agent import Agent
from google.genai import types

from .callbacks import (
    after_model_callback,
    after_tool_callback,
    before_tool_callback,
    configure_logging,
)
from .config import get_settings
from .prompts import build_description, build_instruction
from .tools import ANDROID_TOOLS

APP_NAME = "android_automation_agent"
USER_ID = "local_user"

_settings = get_settings()
configure_logging()

root_agent = Agent(
    name=APP_NAME,
    model=_settings.model,
    description=build_description(),
    instruction=build_instruction(_settings.max_retries, _settings.max_tool_calls),
    tools=ANDROID_TOOLS,
    before_tool_callback=before_tool_callback,
    after_tool_callback=after_tool_callback,
    after_model_callback=after_model_callback,
    # Deterministic tool use matters more than creativity here.
    generate_content_config=types.GenerateContentConfig(temperature=0.0),
)


async def run_task(task: str) -> str:
    """Run one request to completion and return the agent's final response."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    session_service = InMemorySessionService()
    runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)
    session = await session_service.create_session(app_name=APP_NAME, user_id=USER_ID)
    message = types.Content(role="user", parts=[types.Part(text=task)])

    final = ""
    async for event in runner.run_async(
        user_id=USER_ID, session_id=session.id, new_message=message
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final = "".join(part.text or "" for part in event.content.parts)
    return final


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src", description="Run the Android automation agent on one task."
    )
    parser.add_argument("task", nargs="+", help="Natural-language task, e.g. 'Open Brave and search for youtube.com'")
    args = parser.parse_args(argv)
    print(asyncio.run(run_task(" ".join(args.task))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
