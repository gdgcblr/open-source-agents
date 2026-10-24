"""Context Orchestration Engine - entry point.

    python main.py                                   the built-in five-step demo
    python main.py --objective "..." --task "..." --task "..."
    python main.py --stop-after 2                    stop early (state is on disk)
    python main.py --resume task-1a2b                continue a saved task
    python main.py --state task-1a2b                 print canonical state as JSON
    python main.py --list                            list saved tasks

With no API keys configured, runs use the offline mock gateway.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from context_orchestration.compiler import ContextCompiler
from context_orchestration.demo import DEMO_OBJECTIVE, DEMO_PLAN
from context_orchestration.gateway import build_gateway
from context_orchestration.orchestrator import (
    Orchestrator,
    RunSummary,
    TurnResult,
    load_workers,
    missing_keys,
)
from context_orchestration.store import DEFAULT_DB, SQLiteStore


def print_turn(result: TurnResult, show_context: bool) -> None:
    p, r, s = result.package, result.report, result.state
    print(f"\nturn {result.turn}/{len(s.plan)}  {result.worker.id}  {result.worker.model}")
    print(f"  task       {result.assigned_task}")
    print(f"  briefing   {p.estimated_tokens} of {p.budget} tokens, "
          f"{len(p.sections)} sections, omitted: {', '.join(p.omitted_sections) or 'none'}")
    print(f"  reconciled +{r.decisions_added} decisions, "
          f"+{len(r.artifacts_created)} artifacts, {len(r.artifacts_versioned)} versioned, "
          f"+{len(r.issues_opened)} issues, +{r.failed_attempts_added} failed attempts")
    for warning in r.warnings:
        print(f"  warning    {warning}")
    if show_context:
        print("  ---- briefing sent ----")
        print("  " + p.rendered_text.replace("\n", "\n  "))
        print("  -----------------------")


def print_summary(summary: RunSummary, store: SQLiteStore) -> None:
    state = store.load_state(summary.task_id)
    print(f"\n{summary.task_id}  {summary.status}  ({summary.turns}/{summary.steps} steps)")
    print(f"  workers used                {len(summary.workers_used)} ({', '.join(summary.workers_used)})")
    print(f"  raw conversation transfers  {summary.raw_conversation_transfers}")
    print(f"  peak briefing tokens        {summary.peak_package_tokens}")
    print(f"  decisions / artifacts       {len(state.decisions)} / {len(state.artifacts)} "
          f"(artifacts unverified: content is not checked)")
    print(f"  open issues                 {len(state.open_issues())}")
    for issue in state.open_issues():
        claimed = (f" (resolution claimed by {issue.resolution_claimed_by}, unverified)"
                   if issue.resolution_claimed_by else "")
        print(f"    {issue.id} [{issue.severity}] {issue.description}{claimed}")
    if summary.status != "completed":
        print(f"\n  State is saved. Continue with: python main.py --resume {summary.task_id}")


def build_orchestrator(args, store: SQLiteStore) -> Orchestrator:
    workers = load_workers(args.workers)
    missing = missing_keys(workers)
    mock = args.mock or (not args.real and bool(missing))
    if mock and not args.mock:
        print(f"No key for {', '.join(missing)}: using the offline MOCK gateway. "
              "Set keys in .env (see .env.example) and pass --real for live calls.")
    return Orchestrator(
        workers,
        build_gateway(mock),
        store,
        compiler=ContextCompiler(budget=args.budget),
        on_turn=lambda result: print_turn(result, args.show_context),
    )


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Context Orchestration Engine")
    parser.add_argument("--objective", help="task objective (requires at least one --task)")
    parser.add_argument("--task", action="append", help="a plan step; repeat for more")
    parser.add_argument("--resume", metavar="TASK_ID", help="continue a saved task (prefix is enough)")
    parser.add_argument("--state", metavar="TASK_ID", help="print a task's canonical state as JSON")
    parser.add_argument("--list", action="store_true", help="list saved tasks")
    parser.add_argument("--stop-after", type=int, metavar="N", help="stop after N worker turns")
    parser.add_argument("--mock", action="store_true", help="force the offline mock gateway")
    parser.add_argument("--real", action="store_true", help="force live model calls")
    parser.add_argument("--budget", type=int, default=1200, help="token budget per briefing (default 1200)")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"SQLite file (default {DEFAULT_DB})")
    parser.add_argument("--workers", help="worker roster JSON (default ./workers.json, else the example)")
    parser.add_argument("--show-context", action="store_true", help="print every briefing sent")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    with SQLiteStore(args.db) as store:
        if args.list:
            rows = store.tasks()
            if not rows:
                print("No saved tasks yet. Try: python main.py")
            for row in rows:
                print(f"{row['task_id']}  {row['status']:<9}  {row['turn']}/{row['steps']}  "
                      f"{row['objective'][:60]}")
            return 0

        if args.state:
            print(json.dumps(store.load_state(store.resolve(args.state)).model_dump(), indent=2))
            return 0

        if args.resume:
            task_id = store.resolve(args.resume)
            orch = build_orchestrator(args, store)
            state = store.load_state(task_id)
            print(f"{task_id}: resuming at step {state.turn + 1} of {len(state.plan)}")
        else:
            plan = args.task or ([] if args.objective else DEMO_PLAN)
            if not plan:
                print("--objective needs at least one --task step.", file=sys.stderr)
                return 2
            objective = args.objective or DEMO_OBJECTIVE
            orch = build_orchestrator(args, store)
            task_id = orch.create_task(objective, plan).task_id
            print(f"{task_id}: {objective}")

        print_summary(orch.run(task_id, max_turns=args.stop_after), store)
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv(Path.cwd() / ".env")
    except ImportError:  # pragma: no cover - listed in requirements.txt
        pass
    try:
        return run(parse_args(argv))
    except KeyError as exc:
        print(exc.args[0] if exc.args else exc, file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
