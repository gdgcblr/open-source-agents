"""Live evals for Invoice Chaser (needs GOOGLE_API_KEY).

    python -m evals.run_evals                     # all suites
    python -m evals.run_evals --suite matcher     # matcher | drafter | scenarios
    python -m evals.run_evals --repeat 3          # run each suite 3x (model variance)

Writes evals/results/<timestamp>.json and .md. Every number in the report comes
from the ledger state after the agent ran, not from what the agent said.
"""

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from evals import scoring  # noqa: E402
from ledger import Ledger, LedgerConfig  # noqa: E402

SAMPLE = PROJECT_DIR / "sample_data"
DATA = Path(__file__).resolve().parent / "data"
RESULTS = Path(__file__).resolve().parent / "results"
TODAY = "2026-10-24"  # the sample data is written for this date


# ------------------------------------------------------------------ plumbing

def fresh_ledger(tmp: Path, with_payments: bool = True) -> Path:
    db = tmp / "ledger.db"
    led = Ledger(db, LedgerConfig.from_env())
    led.import_clients(str(SAMPLE / "clients.csv"))
    led.import_invoices(str(SAMPLE / "invoices.csv"))
    if with_payments:
        led.import_payments(str(SAMPLE / "bank_statement.csv"))
    led.close()
    os.environ["INVOICE_CHASER_DB"] = str(db)  # read by the MCP server the agent spawns
    return db


async def run_agent(agent, messages: list[str]) -> list[dict]:
    """Run messages in one session. Returns per-message {events, state, final_text}."""
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    runner = InMemoryRunner(agent=agent, app_name="eval")
    session = await runner.session_service.create_session(app_name="eval", user_id="owner")
    turns = []
    try:
        for message in messages:
            events = []
            async for ev in runner.run_async(
                    user_id="owner", session_id=session.id,
                    new_message=types.Content(role="user", parts=[types.Part.from_text(text=message)])):
                events.append(ev)
            state = (await runner.session_service.get_session(
                app_name="eval", user_id="owner", session_id=session.id)).state
            turns.append({"events": events, "state": dict(state),
                          "final_text": scoring.final_text(events, agent.name)})
    finally:
        await runner.close()
    return turns


# -------------------------------------------------------------------- suites

def suite_matcher(model=None, only: list[str] | None = None) -> dict:
    from invoice_chaser.agent import build_matcher

    cases = json.loads((DATA / "matcher_cases.json").read_text())["cases"]
    if only:
        cases = [c for c in cases if c["id"] in only]
    results = []
    for case in cases:
        with tempfile.TemporaryDirectory() as tmp:
            db = fresh_ledger(Path(tmp), with_payments=False)
            bank = Path(tmp) / "bank.csv"
            bank.write_text("date,narration,ref,credit,debit,currency\n"
                            f"{case['date']},\"{case['narration']}\",{case['id']},{case['amount']},,"
                            f"{case['currency']}\n", encoding="utf-8")
            Ledger(db, LedgerConfig.from_env()).import_payments(str(bank))
            started = time.time()
            try:
                asyncio.run(run_agent(build_matcher(model, mode=None), ["Match new payments."]))
                error = None
            except Exception as e:  # recorded, not hidden: the case counts as failed
                error = f"{type(e).__name__}: {e}"
            outcome = scoring.matcher_outcome(Ledger(db, LedgerConfig.from_env()))
            results.append({"id": case["id"], "tag": case["tag"], "expected": case["expected"],
                            "outcome": outcome, "error": error,
                            "seconds": round(time.time() - started, 1),
                            **scoring.score_matcher_case(case["expected"], outcome, error)})
        print(f"  {case['id']} {case['tag']:<28} {'PASS' if results[-1]['passed'] else 'FAIL'}"
              f"{'  CRITICAL' if results[-1]['critical'] else ''}")
    return {"cases": results, "metrics": scoring.matcher_metrics(results)}


def suite_drafter(model=None, judge_model=None) -> dict:
    from invoice_chaser.agent import build_drafter

    with tempfile.TemporaryDirectory() as tmp:
        db = fresh_ledger(Path(tmp))
        led = Ledger(db, LedgerConfig.from_env())
        expected = [i for i in led.get_chase_list()["items"] if i["can_queue_reminder"]]
        error = None
        try:
            turns = asyncio.run(run_agent(build_drafter(model, mode=None), ["Draft today's reminders."]))
            rejections = scoring.count_tool_errors(turns[0]["events"], "queue_reminder", "RENDER_REJECTED")
        except Exception as e:
            error, rejections = f"{type(e).__name__}: {e}", None
        queued = {r["invoice_id"]: r for r in led.list_reminders("QUEUED")["reminders"]}

    drafts = []
    for item in expected:
        rem = queued.get(item["invoice_id"])
        row = {"invoice_id": item["invoice_id"], "expected_tone": item["recommended_tone"],
               "expected_language": item["language"], "queued": rem is not None}
        if rem:
            row.update(scoring.rule_checks(rem, item))
            row["judge"] = scoring.judge_draft(rem, item, judge_model)
        drafts.append(row)
        print(f"  {item['invoice_id']} tone {item['recommended_tone']} {item['language']:<9}"
              f"{'queued' if rem else 'NOT QUEUED'}"
              f"{'  judge ' + str(row.get('judge', {}).get('mean')) if rem else ''}")
    return {"drafts": drafts, "render_rejections": rejections, "error": error,
            "metrics": scoring.drafter_metrics(drafts)}


def suite_scenarios(model=None) -> dict:
    from invoice_chaser.agent import build_root_agent

    scenarios = []
    with tempfile.TemporaryDirectory() as tmp:
        db = fresh_ledger(Path(tmp))
        error = None
        try:
            turns = asyncio.run(run_agent(build_root_agent(model),
                                          ["Run today's chase.", "Run today's chase again."]))
        except Exception as e:
            error, turns = f"{type(e).__name__}: {e}", []
        led = Ledger(db, LedgerConfig.from_env())
        scenarios.append(scoring.scenario_sample_chase(led, turns[0] if turns else None, error))
        scenarios.append(scoring.scenario_rerun(led, turns, error))
    for s in scenarios:
        print(f"  {s['id']} {s['name']:<40} {'PASS' if s['passed'] else 'FAIL'}")
        for check, ok in s["checks"].items():
            print(f"      {'✓' if ok else '✗'} {check}")
    return {"scenarios": scenarios,
            "metrics": {"passed": sum(s["passed"] for s in scenarios), "total": len(scenarios)}}


# -------------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=["matcher", "drafter", "scenarios", "all"], default="all")
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()

    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_DIR / ".env")
    except ImportError:
        pass
    if not os.getenv("GOOGLE_API_KEY") and os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").upper() != "TRUE":
        print("GOOGLE_API_KEY is not set (see .env.example). The offline tests are: pytest")
        return 1
    os.environ["INVOICE_CHASER_TODAY"] = TODAY

    from invoice_chaser import prompts
    from invoice_chaser.agent import DEFAULT_MODEL
    model = os.getenv("MODEL_NAME") or DEFAULT_MODEL
    report = {"started": datetime.now().isoformat(timespec="seconds"), "model": model,
              "judge_model": os.getenv("JUDGE_MODEL") or model,
              "prompt_version": prompts.PROMPT_VERSION, "runs": []}
    suites = ["matcher", "drafter", "scenarios"] if args.suite == "all" else [args.suite]
    for n in range(args.repeat):
        run = {}
        for suite in suites:
            print(f"\n== {suite} (run {n + 1}/{args.repeat}) ==")
            if suite == "matcher":
                run[suite] = suite_matcher()
            elif suite == "drafter":
                run[suite] = suite_drafter(judge_model=report["judge_model"])
            else:
                run[suite] = suite_scenarios()
        report["runs"].append(run)

    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (RESULTS / f"{stamp}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    md = scoring.markdown_report(report)
    (RESULTS / f"{stamp}.md").write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"Saved evals/results/{stamp}.md")
    return 0 if scoring.all_thresholds_met(report) else 2


if __name__ == "__main__":
    sys.exit(main())
