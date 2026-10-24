"""
main.py – Planning Puppet: interactive CLI entry point.

Run this file to start a multi-turn conversation with Planning Puppet in your
terminal.  After each agent response the plan is automatically sent to the
LLM-as-a-Judge evaluator, and a quality report is printed.

Usage
-----
    python main.py

Environment Variables Required
-------------------------------
    GEMINI_API_KEY  – Your Google AI Studio or Vertex AI API key.

Optional
--------
    MODEL_NAME      – LLM model identifier (default: gemini-2.5-flash).
    EVALUATOR_MODEL – Separate model for the evaluator (default: MODEL_NAME).
"""

from __future__ import annotations

import asyncio
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.text import Text

# Local imports
from agent import root_agent
from evaluator import evaluate_plan, format_evaluation_report

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv()
console = Console()

APP_NAME = "planning-puppet"
USER_ID = "host-user"
EVALUATE_RESPONSES = os.getenv("ENABLE_EVALUATOR", "true").lower() == "true"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_banner() -> None:
    banner = Text()
    banner.append("🎉  Planning Puppet\n", style="bold magenta")
    banner.append(
        "Your AI-powered event planning concierge for weddings, birthdays & community events.",
        style="dim",
    )
    console.print(Panel(banner, border_style="magenta", padding=(1, 4)))
    console.print(
        "[dim]Type [bold]exit[/bold] or [bold]quit[/bold] to end the session.  "
        "Type [bold]eval off[/bold] to disable the quality evaluator.[/dim]\n"
    )


def _print_agent_response(text: str) -> None:
    console.print(Rule("[bold cyan]Planning Puppet[/bold cyan]", style="cyan"))
    console.print(Markdown(text))
    console.print()


def _print_evaluation(plan_text: str) -> None:
    if not EVALUATE_RESPONSES:
        return
    with console.status("[dim]Running LLM-as-a-Judge evaluation…[/dim]", spinner="dots"):
        result = evaluate_plan(plan_text)
    report = format_evaluation_report(result)
    console.print(report)


# ---------------------------------------------------------------------------
# Core conversation loop
# ---------------------------------------------------------------------------


async def run_conversation() -> None:
    """Start and manage an interactive multi-turn conversation."""
    global EVALUATE_RESPONSES  # allow toggle at runtime

    # Guard: ensure API key is present
    if not os.getenv("GEMINI_API_KEY"):
        console.print(
            "[bold red]Error:[/bold red] GEMINI_API_KEY is not set.\n"
            "Copy [bold].env.example[/bold] to [bold].env[/bold] and add your key."
        )
        sys.exit(1)

    # Set up ADK session and runner
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        state={},
    )

    runner = Runner(
        app_name=APP_NAME,
        agent=root_agent,
        session_service=session_service,
    )

    _print_banner()

    # ── Conversation loop ────────────────────────────────────────────────────
    while True:
        try:
            user_input = Prompt.ask("[bold green]You[/bold green]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye!  Happy planning! 🎊[/dim]")
            break

        if not user_input:
            continue

        # Runtime commands
        if user_input.lower() in ("exit", "quit"):
            console.print("[dim]Goodbye!  Happy planning! 🎊[/dim]")
            break
        if user_input.lower() == "eval off":
            EVALUATE_RESPONSES = False
            console.print("[dim]Quality evaluator disabled for this session.[/dim]")
            continue
        if user_input.lower() == "eval on":
            EVALUATE_RESPONSES = True
            console.print("[dim]Quality evaluator enabled.[/dim]")
            continue

        # Build message content
        content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_input)],
        )

        # Stream agent response
        console.print()
        full_response_text = ""

        with console.status("[dim]Planning Puppet is thinking…[/dim]", spinner="bouncingBar"):
            async for event in runner.run_async(
                user_id=USER_ID,
                session_id=session.id,
                new_message=content,
            ):
                # Collect the final model response text
                if hasattr(event, "content") and event.content:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            full_response_text = part.text

        if full_response_text:
            _print_agent_response(full_response_text)
            _print_evaluation(full_response_text)
        else:
            console.print("[dim](No text response received — the agent may have called tools only.)[/dim]\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    asyncio.run(run_conversation())
