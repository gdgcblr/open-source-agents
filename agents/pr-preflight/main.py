"""PR Preflight CLI: python main.py <project_path> [--out DIR]"""
import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")  # GOOGLE_API_KEY for the agent; never printed

from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

from checks import print_results, redact, run_checks  # noqa: E402
from preflight_agent.agent import root_agent  # noqa: E402
from report import write_report  # noqa: E402
from sandbox import cleanup_sandbox, create_sandbox  # noqa: E402

APP, USER = "preflight_agent", "contributor"
ATTEMPTS = 3
AGENT_TIMEOUT = 240  # seconds per attempt; model calls can hang under load


async def run_agent(sandbox: Path) -> tuple[str, dict]:
    svc = InMemorySessionService()
    state = {"sandbox": str(sandbox), "runs": [], "blocked": [], "calls": 0, "tool_log": []}
    session = await svc.create_session(app_name=APP, user_id=USER, state=state)
    message = types.Content(role="user", parts=[types.Part(text="Test this project.")])
    final = []
    async with Runner(app_name=APP, agent=root_agent, session_service=svc) as runner:
        async for ev in runner.run_async(user_id=USER, session_id=session.id, new_message=message):
            if ev.is_final_response() and ev.content and ev.content.parts:
                final += [p.text for p in ev.content.parts if p.text]
    session = await svc.get_session(app_name=APP, user_id=USER, session_id=session.id)
    return "\n".join(final), dict(session.state)


def compute_verdict(checks: list[dict], state: dict, agent_error: str | None):
    """Deterministic verdict from facts; the LLM's words never count."""
    runs, reasons, warnings = state.get("runs", []), [], []
    reasons += [f"check {c['id']} failed" for c in checks if c["status"] == "fail"]
    reasons += [f"`{r['command']}` exited with {r['exit_code']}" for r in runs if r["exit_code"] != 0]
    if not any(r["exit_code"] == 0 for r in runs):
        reasons.append("no command ran successfully in the sandbox")
    if state.get("calls", 0) == 0:
        warnings.append("⚠️ agent made no tool calls")
    if agent_error:
        warnings.append(f"⚠️ agent error: {agent_error}")
    warnings += [f"🛡️ blocked {b['tool']}: {b['reason']}" for b in state.get("blocked", [])]
    return ("FAIL" if reasons else "PASS"), reasons, warnings


async def preflight(project_path: str, out_dir=".") -> dict:
    checks = run_checks(project_path)
    sandbox = create_sandbox(project_path)
    diagnosis, state, agent_error = "", {}, None
    try:
        for attempt in range(1, ATTEMPTS + 1):  # model 503s are common under load
            try:
                diagnosis, state = await asyncio.wait_for(run_agent(sandbox), AGENT_TIMEOUT)
                agent_error = None
                break
            except Exception as e:  # keep going so the report explains what happened
                agent_error = redact(f"{type(e).__name__}: {e}")[:500] or type(e).__name__
                if attempt < ATTEMPTS:
                    print(f"agent attempt {attempt} failed ({type(e).__name__}); retrying...",
                          flush=True)
                    await asyncio.sleep(5 * attempt)
    finally:
        cleanup_sandbox(sandbox)
    verdict, reasons, warnings = compute_verdict(checks, state, agent_error)
    result = {"project": str(Path(project_path).resolve()), "verdict": verdict,
              "reasons": reasons, "warnings": warnings, "checks": checks,
              "runs": state.get("runs", []), "blocked": state.get("blocked", []),
              "calls": state.get("calls", 0), "tool_log": state.get("tool_log", []),
              "diagnosis": redact(diagnosis), "agent_error": agent_error}
    result["report_path"] = str(write_report(result, out_dir))
    return result


def print_summary(result: dict) -> None:
    print_results(result["checks"])
    for r in result["runs"]:
        print(f"{'✅' if r['exit_code'] == 0 else '❌'} ran `{r['command']}` -> exit {r['exit_code']}")
    for w in result["warnings"]:
        print(w)
    for reason in result["reasons"]:
        print(f"   - {reason}")
    print(f"\nVERDICT: {result['verdict']}  (tool calls: {result['calls']})")
    print(f"Report: {result['report_path']}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Check a project before opening a PR.")
    ap.add_argument("project_path")
    ap.add_argument("--out", default=".", help="folder for preflight-report.md")
    args = ap.parse_args()
    res = asyncio.run(preflight(args.project_path, args.out))
    print_summary(res)
    sys.exit(0 if res["verdict"] == "PASS" else 1)
