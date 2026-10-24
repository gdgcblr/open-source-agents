"""Command-line entry point.

    python main.py agents/my-project                 # full AI review (needs GOOGLE_API_KEY)
    python main.py agents/my-project --checks-only   # deterministic checks, no LLM
"""

import argparse
import asyncio
import json
import logging
import sys

from contribution_reviewer.checks import format_report, resolve_project, run_all_checks


async def ai_review(project_path: str, base_ref: str) -> str:
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    from contribution_reviewer.agent import root_agent

    runner = InMemoryRunner(agent=root_agent, app_name="contribution_reviewer")
    session = await runner.session_service.create_session(app_name="contribution_reviewer", user_id="cli")
    message = types.Content(
        role="user",
        parts=[types.Part(text=f"Review the contribution at '{project_path}'. Use base ref '{base_ref}'.")],
    )
    final = ""
    async for event in runner.run_async(user_id="cli", session_id=session.id, new_message=message):
        if event.is_final_response() and event.content and event.content.parts:
            final = "".join(p.text or "" for p in event.content.parts)
    await runner.close()
    return final


def main() -> int:
    parser = argparse.ArgumentParser(description="Review an open-source-agents contribution.")
    parser.add_argument("project_path", help='Contribution folder, e.g. "agents/my-project"')
    parser.add_argument("--base", default="upstream/main", help="Git ref the PR targets (default: upstream/main)")
    parser.add_argument("--checks-only", action="store_true", help="Run deterministic checks without the LLM")
    parser.add_argument("--json", action="store_true", help="With --checks-only, print raw JSON results")
    args = parser.parse_args()

    try:
        resolve_project(args.project_path)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.checks_only:
        results = run_all_checks(args.project_path, args.base)
        print(json.dumps(results, indent=2) if args.json else format_report(results))
        return 0 if all(r["passed"] for r in results) else 1

    from google.genai.errors import APIError

    # ADK logs a full traceback for model errors; we report them concisely below.
    logging.getLogger("google_adk").setLevel(logging.CRITICAL)
    try:
        print(asyncio.run(ai_review(args.project_path, args.base)))
    except APIError as exc:
        print(f"Gemini API error {exc.code}: {exc.message}", file=sys.stderr)
        print("Tip: run with --checks-only to review without the model.", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
