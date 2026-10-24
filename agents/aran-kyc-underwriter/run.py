"""Run the underwriter on a case folder and restore real values locally at the end.

    uv run python run.py                     # sample case from the Aran tool
    uv run python run.py --case /path/docs   # your own (local) documents
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

console = Console()
MAX_LLM_CALLS = 25  # G5: hard budget per case
VERDICTS = {"ELIGIBLE", "REFER", "DECLINE"}


def parse_report(text: str) -> dict | None:
    """Extract and sanity-check the JSON block from the agent's reply."""
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S) or re.search(r"(\{.*\})", text, re.S)
    if not m:
        return None
    try:
        report = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    if report.get("verdict") not in VERDICTS:
        return None
    if report["verdict"] != "ELIGIBLE":
        report["requires_human_review"] = True  # G6: never trust the model to waive review
    return report


async def run_case(case: str | None, ask: str, quiet: bool = False) -> dict:
    if case:
        os.environ["CASE_DIR"] = case

    # Imported after CASE_DIR is set; the agent module fixes the session at import time.
    from google.adk.agents.run_config import RunConfig
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    import aran
    from kyc_underwriter.agent import SESSION_ID, root_agent

    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        sys.exit("Set GEMINI_API_KEY (see .env.example).")

    runner = InMemoryRunner(agent=root_agent, app_name="aran_kyc")
    session = await runner.session_service.create_session(app_name="aran_kyc", user_id="analyst")
    message = types.Content(role="user", parts=[types.Part(text=ask)])

    final, tool_calls = "", []
    async for event in runner.run_async(
        user_id="analyst", session_id=session.id, new_message=message,
        run_config=RunConfig(max_llm_calls=MAX_LLM_CALLS),
    ):
        for part in (event.content.parts if event.content else None) or []:
            if part.function_call:
                tool_calls.append({"name": part.function_call.name, "args": dict(part.function_call.args or {})})
                if not quiet:
                    console.print(f"[cyan]→ tool[/] {part.function_call.name}({tool_calls[-1]['args']})")
            elif part.function_response and not quiet:
                console.print(f"[green]← tool[/] {part.function_response.name} [dim](redacted text returned)[/]")
            elif part.text and event.is_final_response():
                final += part.text
    await runner.close()

    restored = aran.restore(final, SESSION_ID)
    return {
        "session_id": SESSION_ID,
        "model_output": final,
        "restored_output": restored,
        "report": parse_report(final),
        "tool_calls": tool_calls,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Aran KYC underwriter")
    parser.add_argument("--case", help="Folder with the applicant's documents")
    parser.add_argument("--ask", default="Pre-screen this loan applicant.")
    args = parser.parse_args()

    result = await run_case(args.case, args.ask)
    console.print(Panel(escape(result["model_output"]), title="What Gemini produced (tokens only)", border_style="yellow"))
    console.print(Panel(
        escape(result["restored_output"]),
        title=f"Restored locally by Aran (session {result['session_id']})", border_style="green",
    ))
    report = result["report"]
    if report is None:
        console.print("[red]The agent did not return a valid report JSON; treat this case as REFER.[/]")
    else:
        review = " - human review required" if report.get("requires_human_review") else ""
        console.print(f"[bold]Verdict:[/] {report['verdict']}{review}")


if __name__ == "__main__":
    asyncio.run(main())
