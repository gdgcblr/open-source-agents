"""Run a guided, live LifeAdmin demonstration with a local Ollama model."""

from __future__ import annotations

import argparse
import asyncio
import gc
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

from lifeadmin_mcp import storage


def _next_november_tenth(today: date) -> date:
    year = today.year if (today.month, today.day) <= (11, 10) else today.year + 1
    return date(year, 11, 10)


def _ollama_model_info(api_base: str, requested_model: str) -> tuple[str, str]:
    endpoint = f"{api_base.rstrip('/')}/api/tags"
    request = urllib.request.Request(endpoint, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"Cannot reach Ollama at {api_base}. Start Ollama and try again."
        ) from error

    models = payload.get("models", [])
    for model in models:
        name = model.get("name", "")
        if name == requested_model:
            return endpoint, name
    raise RuntimeError(
        f"Model {requested_model!r} is not installed in Ollama at {api_base}. "
        f"Install it with: ollama pull {requested_model}"
    )


def _response_text(content: Any) -> str:
    if content is None:
        return ""
    return "\n".join(
        part.text
        for part in content.parts or []
        if part.text and not getattr(part, "thought", False)
    )


async def _run_prompt(
    runner: Any,
    session_service: Any,
    prompt: str,
    session_number: int,
) -> tuple[str, list[dict[str, Any]]]:
    from google.genai import types

    user_id = f"lifeadmin-demo-{session_number}"
    session = await session_service.create_session(
        app_name="lifeadmin_agent",
        user_id=user_id,
    )
    message = types.Content(role="user", parts=[types.Part(text=prompt)])
    tool_calls: list[dict[str, Any]] = []
    response_text = ""
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=message,
    ):
        for call in event.get_function_calls():
            tool_calls.append({"name": call.name, "args": call.args or {}})
        if event.is_final_response():
            response_text = _response_text(event.content)
    return response_text, tool_calls


async def _run_demo(database_path: Path) -> bool:
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    os.environ["LIFEADMIN_DB_PATH"] = str(database_path)
    storage.list_reminders(status="all")

    from lifeadmin_agent.agent import create_agent

    session_service = InMemorySessionService()
    runner = Runner(
        agent=create_agent(),
        app_name="lifeadmin_agent",
        session_service=session_service,
    )
    target_date = _next_november_tenth(date.today())
    clear_prompt = "Remind me to renew my vehicle insurance on 10 November."
    vague_prompt = "Remind me to renew my insurance sometime next month."

    try:
        print("\nDEMO 1 / A clear natural-language deadline")
        print(f"You: {clear_prompt}")
        response, calls = await _run_prompt(runner, session_service, clear_prompt, 1)
        print(f"Gemma: {response}")
        print("MCP tool calls:")
        for call in calls:
            print(f"  {call['name']}({json.dumps(call['args'], ensure_ascii=False)})")

        reminders = storage.list_reminders(status="all")
        saved = [
            reminder
            for reminder in reminders
            if "vehicle insurance" in str(reminder["title"]).casefold()
            and reminder["due_date"] == target_date.isoformat()
            and reminder["status"] == "open"
        ]
        saved_ok = bool(saved) and any(call["name"] == "add_reminder" for call in calls)
        print(
            "SQLite verification: "
            + (
                f"PASS - {saved[0]['title']} due {saved[0]['due_date']} is saved locally."
                if saved_ok
                else "FAIL — expected reminder was not saved through add_reminder."
            )
        )

        print("\nDEMO 2 / An ambiguous date")
        print(f"You: {vague_prompt}")
        reminders_before = storage.list_reminders(status="all")
        response, calls = await _run_prompt(runner, session_service, vague_prompt, 2)
        print(f"Gemma: {response}")
        print("MCP tool calls:")
        if calls:
            for call in calls:
                print(f"  {call['name']}({json.dumps(call['args'], ensure_ascii=False)})")
        else:
            print("  (none - the assistant asked before writing)")
        reminders_after = storage.list_reminders(status="all")
        no_write_ok = (
            not any(call["name"] == "add_reminder" for call in calls)
            and reminders_after == reminders_before
        )
        print(
            "SQLite verification: "
            + (
                "PASS - the vague request did not add or alter a reminder."
                if no_write_ok
                else "FAIL — the database changed during the vague-date scenario."
            )
        )

        print("\nEND-TO-END FLOW")
        print("  You -> Google ADK -> Gemma via Ollama -> LifeAdmin MCP tools -> SQLite")
        print(f"  Ollama model: {os.environ['LIFEADMIN_MODEL']}")
        print(f"  Database: {database_path}")
        return saved_ok and no_write_ok
    finally:
        await runner.close()
        await asyncio.sleep(0.2)
        gc.collect()


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace", line_buffering=True)
    try:
        from dotenv import load_dotenv
        from google.adk.runners import Runner as _Runner  # noqa: F401
        from google.adk.sessions import InMemorySessionService as _SessionService  # noqa: F401
    except ImportError:
        raise SystemExit(
            'install the agent dependencies first: python -m pip install -e ".[agent]"'
        ) from None

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        default=os.getenv("LIFEADMIN_MODEL", "gemma4:e4b"),
        help="Installed local Ollama model tag (default: gemma4:e4b).",
    )
    parser.add_argument(
        "--ollama-api-base",
        default=os.getenv("OLLAMA_API_BASE", "http://localhost:11434"),
        help="Local Ollama API base URL.",
    )
    args = parser.parse_args()

    try:
        endpoint, installed_model = _ollama_model_info(args.ollama_api_base, args.model)
        os.environ["LIFEADMIN_MODEL"] = args.model
        os.environ["OLLAMA_API_BASE"] = args.ollama_api_base
        demo_dir = Path(tempfile.mkdtemp(prefix="lifeadmin-demo-"))
        database_path = demo_dir / "reminders.sqlite3"

        print("LIFEADMIN / LIVE LOCAL AI DEMO")
        print(f"  Agent framework: Google ADK")
        print(f"  Model: {args.model} (installed in Ollama as {installed_model})")
        print(f"  Ollama API: {endpoint}")
        print("  MCP: LifeAdmin stdio server (started by the agent)")
        print("  Storage: isolated local SQLite database")
        print(f"  Database path: {database_path}")
        print("\nBoth prompts below are sent live to the configured model.")
        success = asyncio.run(_run_demo(database_path))
    except (OSError, RuntimeError, ValueError) as error:
        print(f"lifeadmin-demo: {error}", file=sys.stderr)
        raise SystemExit(2) from error

    print(f"\nDemo verification: {'PASS' if success else 'FAIL'}")
    if not success:
        raise SystemExit(1)
    print("The isolated demo database is kept so you can inspect it after the presentation.")
    print("PowerShell verification:")
    print(f'  $env:LIFEADMIN_DB_PATH = "{database_path}"')
    print("  lifeadmin list --status all")


if __name__ == "__main__":
    main()
