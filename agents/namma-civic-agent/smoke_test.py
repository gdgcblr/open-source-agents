"""Run the agent once from the command line, without the web UI.

Prints every tool call, the agent's reply and the tokens used, so reviewers
can check behaviour quickly and reproducibly.

Usage:
    python smoke_test.py "Pothole on 80 Feet Road, Koramangala 4th Block"
    python smoke_test.py --image examples/pothole.jpg "Near Indiranagar metro"
"""

import argparse
import asyncio
import mimetypes
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from namma_civic_agent.agent import root_agent  # noqa: E402


def build_message(text: str, image: Path | None) -> types.Content:
    parts = [types.Part(text=text)]
    if image:
        mime_type = mimetypes.guess_type(image)[0] or "image/jpeg"
        parts.insert(0, types.Part.from_bytes(data=image.read_bytes(), mime_type=mime_type))
    return types.Content(role="user", parts=parts)


async def main(text: str, image: Path | None) -> None:
    runner = InMemoryRunner(agent=root_agent, app_name="namma_civic_agent")
    session = await runner.session_service.create_session(
        app_name="namma_civic_agent", user_id="smoke-test"
    )

    requests = prompt_tokens = output_tokens = 0
    async for event in runner.run_async(
        user_id="smoke-test", session_id=session.id, new_message=build_message(text, image)
    ):
        if event.usage_metadata:
            requests += 1
            prompt_tokens += event.usage_metadata.prompt_token_count or 0
            output_tokens += event.usage_metadata.candidates_token_count or 0
        for part in (event.content.parts if event.content else None) or []:
            if part.function_call:
                print(f"[tool call] {part.function_call.name}({dict(part.function_call.args)})")
            elif part.text:
                print(part.text)

    print(
        f"\n[usage] model requests: {requests}, input tokens: {prompt_tokens}, "
        f"output tokens: {output_tokens}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("message", help="Describe the problem and where it is")
    parser.add_argument("--image", type=Path, help="Optional photo of the problem")
    args = parser.parse_args()
    if args.image and not args.image.is_file():
        parser.error(f"image not found: {args.image}")
    asyncio.run(main(args.message, args.image))
