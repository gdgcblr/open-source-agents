"""Runs the README drafter once from the terminal, without the web UI.

Usage:
    python -m readme_drafter.cli                          # "Draft a README for this project."
    python -m readme_drafter.cli "Focus on the CLI usage"  # custom request
"""

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

# Same .env as `adk web` and Docker Compose; loaded before the agent reads its settings.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from .agent import root_agent  # noqa: E402

APP_NAME = "readme_drafter"
DEFAULT_REQUEST = "Draft a README for this project."


def _short(args: dict) -> str:
    return ", ".join(
        f"{key}={value!r}" if len(str(value)) <= 60 else f"{key}=<{len(str(value))} chars>"
        for key, value in (args or {}).items()
    )


async def main(request: str) -> int:
    runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(app_name=APP_NAME, user_id="cli")
    message = types.Content(role="user", parts=[types.Part(text=request)])

    reply = ""
    async for event in runner.run_async(user_id="cli", session_id=session.id, new_message=message):
        for call in event.get_function_calls():
            print(f"-> {call.name}({_short(call.args)})", flush=True)
        if not (event.is_final_response() and event.content and event.content.parts):
            continue
        text = "".join(part.text or "" for part in event.content.parts if not part.thought)
        if event.author == root_agent.writer.name:
            reply = text
            print("\n" + reply)
        elif text.strip():  # big-project progress and part summaries: one line each
            print(f"   {text.strip().splitlines()[0][:160]}", flush=True)

    if "Saved to" not in reply:
        print("\nNo README draft was produced. Small local models occasionally return an empty "
              "or malformed reply; please run the command again.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(" ".join(sys.argv[1:]) or DEFAULT_REQUEST)))
