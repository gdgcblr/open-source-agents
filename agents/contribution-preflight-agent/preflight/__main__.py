import argparse
import asyncio
import os
import sys

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .agent import build_master
from .reporting import project_name, timestamp_now, write_reports

APP_NAME = "contribution_preflight"
TRUTHY = ("1", "true", "yes", "on")
FORMAT_CHOICES = {"pdf": ("pdf",), "csv": ("csv",), "both": ("csv", "pdf")}


async def run(
    project_path: str,
    use_llm: bool,
    profile: str | None,
    name: str | None,
    out_dir: str,
    formats: tuple[str, ...],
    aspm: bool,
    vuln_scan: bool,
) -> int:
    service = InMemorySessionService()
    runner = Runner(agent=build_master(), app_name=APP_NAME, session_service=service)
    session = await service.create_session(
        app_name=APP_NAME,
        user_id="cli",
        state={
            "project_path": project_path,
            "use_llm": use_llm,
            "profile": profile,
            "aspm": aspm,
            "vuln_scan": vuln_scan,
        },
    )
    message = types.Content(role="user", parts=[types.Part(text="Run preflight")])
    report = None
    async for event in runner.run_async(user_id="cli", session_id=session.id, new_message=message):
        if event.author == "preflight_master" and event.actions and event.actions.state_delta.get("report"):
            report = event.actions.state_delta["report"]
    if report is None:
        sys.stderr.write("Preflight produced no report.\n")
        return 2
    report["project"] = project_name(project_path, name)
    report["generated"] = timestamp_now()
    written = write_reports(report, out_dir, formats)
    sys.stdout.write(f"Verdict: {report['verdict'].upper()}. Saved: {', '.join(path.name for path in written)}\n")
    return 0 if report["verdict"] == "pass" else 1


def main() -> None:
    parser = argparse.ArgumentParser(prog="preflight")
    parser.add_argument("project_path", nargs="?", default="/project")
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--profile", default=os.environ.get("PREFLIGHT_PROFILE") or None)
    parser.add_argument("--name", default=os.environ.get("PROJECT_NAME") or None)
    parser.add_argument("--out-dir", default=os.environ.get("REPORTS_DIR") or "/reports")
    parser.add_argument("--format", choices=sorted(FORMAT_CHOICES), default="both")
    parser.add_argument("--no-aspm", action="store_true")
    parser.add_argument("--vuln-scan", action="store_true", default=os.environ.get("PREFLIGHT_VULN_SCAN", "").lower() in TRUTHY)
    args = parser.parse_args()
    formats = FORMAT_CHOICES[args.format]
    code = asyncio.run(
        run(args.project_path, not args.no_llm, args.profile, args.name, args.out_dir, formats, not args.no_aspm, args.vuln_scan)
    )
    sys.exit(code)


main()
