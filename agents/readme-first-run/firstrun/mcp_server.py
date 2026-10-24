"""MCP server so coding agents can ask FirstRun whether a README still works.

Run it over stdio:  python -m firstrun.mcp_server
Nothing here may print to stdout, that pipe belongs to the protocol.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

import anyio

try:  # mcp 2.x renamed FastMCP to MCPServer
    from mcp.server.mcpserver import Context, MCPServer
except ImportError:  # pragma: no cover - mcp 1.x
    from mcp.server.fastmcp import Context, FastMCP as MCPServer

from . import __version__, agent, rules
from .cli import load_own_dotenv
from .llm import get_llm
from .models import Report
from .source import SourceError, resolve_target

ROOT = Path(__file__).resolve().parents[1]
STAGES = ("understand", "attempt", "investigate", "repair", "verify", "report")
MAX_DIFF_CHARS = 20_000
TAIL_LINES = 20


def runs_dir() -> Path:
    return Path(os.environ.get("FIRSTRUN_RUNS_DIR") or ROOT / "runs").expanduser().resolve()


def _tail(text: str, n: int = TAIL_LINES) -> str:
    return "\n".join(text.rstrip().splitlines()[-n:])


def plan_summary(target: str, subdir: Optional[str] = None, offline: bool = False) -> dict[str, Any]:
    """What FirstRun would run for this project, without running anything."""
    with tempfile.TemporaryDirectory(prefix="firstrun-plan-") as tmp:
        try:
            project_dir, source = resolve_target(target, subdir, Path(tmp))
        except SourceError as exc:
            return {"error": str(exc)}
        llm = None if offline else get_llm()
        plan = agent.understand(project_dir, llm, {})
        return {
            "project": project_dir.name,
            "source": source,
            "readme": plan.readme_path,
            "planner": plan.engine,
            "steps": [
                {"index": s.index, "command": s.command, "kind": s.kind, "readme_line": s.line,
                 "long_running": s.long_running, "provided_by_firstrun": s.provided_by_firstrun}
                for s in plan.steps
            ],
            "skipped": [{"command": s.command, "reason": s.reason, "readme_line": s.line} for s in plan.skipped],
            "required_env": plan.required_env,
            "static_hints": rules.static_hints(project_dir),
            "notes": plan.notes,
        }


def summarize(report: Report, run_dir: Path) -> dict[str, Any]:
    """Compact view of a Report, small enough to hand back to a coding agent."""
    failing = None
    doc = report.documented_run
    failed = doc.failed_step if doc else None
    if failed is not None:
        failing = {
            "index": failed.step.index,
            "command": failed.step.command,
            "readme_line": failed.step.line,
            "status": failed.status,
            "exit_code": failed.exit_code,
            "output_tail": _tail(failed.output),
        }
    diagnoses = []
    for rnd in report.rounds:
        d = rnd.diagnosis
        diagnoses.append({
            "round": rnd.number,
            "category": d.category,
            "summary": d.summary,
            "confidence": d.confidence,
            "engine": d.engine,
            "blocked": d.blocked,
            "missing_env": d.missing_env,
            "evidence": [f"{e.file}:{e.line}: {e.note}" if e.line else f"{e.file}: {e.note}" for e in d.evidence],
            "verification": rnd.verification.status if rnd.verification else None,
        })
    diff = report.final_diff
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n... (diff truncated, see fix.patch in the run folder)"
    return {
        "verdict": report.verdict,
        "headline": report.headline,
        "works_as_documented": report.verdict == "passed",
        "fix_verified": report.verdict == "fixed",
        "metrics": report.metrics,
        "failing_step": failing,
        "diagnoses": diagnoses,
        "diff": diff,
        "error": report.error,
        "run_dir": str(run_dir),
        "report_md": str(run_dir / "report.md"),
    }


def run_and_summarize(
    target: str, subdir: Optional[str] = None, sandbox: str = "docker", offline: bool = False,
    max_rounds: int = 2, pass_env: Optional[list[str]] = None, on_event=None,
) -> dict[str, Any]:
    if sandbox not in ("docker", "local"):
        return {"error": f"sandbox must be 'docker' or 'local', not {sandbox!r}"}
    if not 0 <= max_rounds <= 5:
        return {"error": "max_rounds must be between 0 and 5"}
    env = {name: os.environ[name] for name in (pass_env or []) if name in os.environ}
    settings = agent.Settings(
        sandbox=sandbox, offline=offline, max_rounds=max(1, max_rounds), repair=max_rounds > 0,
        env=env, out_dir=runs_dir(),
    )
    report, run_dir = agent.run_check(target, settings, subdir=subdir,
                                      on_event=on_event or agent.noop_event)
    return summarize(report, run_dir)


def read_report(run_dir: str) -> str:
    base = runs_dir()
    path = Path(run_dir).expanduser()
    path = (path if path.is_absolute() else base / path).resolve()
    if path != base and base not in path.parents:
        raise ValueError(f"{run_dir} is not inside the FirstRun runs folder ({base})")
    report_md = path / "report.md"
    if not report_md.is_file():
        raise ValueError(f"no report.md in {path}")
    return report_md.read_text(encoding="utf-8")


def _progress_bridge(ctx: Optional[Context]):
    """Turn FirstRun stage events (from the worker thread) into MCP progress notifications."""
    if ctx is None:
        return None
    current = [0]

    def on_event(kind: str, message: str, data: Optional[dict] = None) -> None:
        # MCP logging is deprecated (SEP-2577), so warnings and tool calls ride on progress messages
        try:
            if kind == "stage" and data and data.get("state") == "start" and data.get("stage") in STAGES:
                current[0] = STAGES.index(data["stage"])
                anyio.from_thread.run(ctx.report_progress, current[0], len(STAGES), data["stage"])
            elif kind in ("warn", "tool_call", "step_start"):
                anyio.from_thread.run(ctx.report_progress, current[0], len(STAGES), message[:200])
        except Exception:
            # progress is a nicety, a client that ignores it must not break the run
            pass

    return on_event


def build_server() -> MCPServer:
    server = MCPServer(
        "firstrun",
        instructions=(
            "FirstRun checks whether a newcomer can set up and run a Python project by following "
            "its README in a fresh sandbox. Call firstrun_plan first if you only want to see which "
            "commands it would run. firstrun_check executes the README's commands, so it can take "
            "a few minutes. Use absolute paths or GitHub URLs for targets."
        ),
    )

    @server.tool(description=(
        "List the shell commands a newcomer would run from the project's README, in order, plus the "
        "lines FirstRun would skip and why. Nothing is executed. target is an absolute folder path "
        "or a GitHub URL; subdir picks a project inside a monorepo, e.g. agents/my-agent."
    ))
    async def firstrun_plan(target: str, subdir: Optional[str] = None) -> dict:
        return await anyio.to_thread.run_sync(lambda: plan_summary(target, subdir))

    @server.tool(description=(
        "Run the README's setup and run commands in a fresh sandbox, keep the first failure, "
        "diagnose it, try a minimal fix (README, requirements.txt, .env.example) and verify the fix "
        "in another fresh sandbox. Returns the verdict (passed, fixed, blocked, failed, error), the "
        "failing step, diagnoses with file:line evidence and the patch. sandbox='docker' (default) "
        "isolates everything in a throwaway container; sandbox='local' runs the README's commands on "
        "this machine in a temp folder and venv, use it only for trusted projects. max_rounds=0 means "
        "report only, no fix attempts. pass_env lists environment variable names (from the server's "
        "environment) to pass into the sandbox, for projects that need an API key."
    ))
    async def firstrun_check(
        target: str, subdir: Optional[str] = None, sandbox: str = "docker", offline: bool = False,
        max_rounds: int = 2, pass_env: Optional[list[str]] = None, ctx: Optional[Context] = None,
    ) -> dict:
        on_event = _progress_bridge(ctx)
        return await anyio.to_thread.run_sync(
            lambda: run_and_summarize(target, subdir, sandbox, offline, max_rounds, pass_env, on_event)
        )

    @server.tool(description=(
        "Return the full markdown report of a finished FirstRun check. run_dir is the run_dir value "
        "from firstrun_check, or a run folder name inside FirstRun's runs folder."
    ))
    def firstrun_report(run_dir: str) -> str:
        return read_report(run_dir)

    return server


def main() -> None:
    load_own_dotenv()
    print(f"firstrun MCP server {__version__} on stdio, runs in {runs_dir()}", file=sys.stderr)
    build_server().run("stdio")


if __name__ == "__main__":
    main()
