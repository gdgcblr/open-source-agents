"""Monarch engineering team (Architect, Junior, Senior on Google ADK) - the one entry point.

    python main.py                                   interactive CLI
    python main.py ask "clone https://github.com/o/r and fix: crash on empty input"
    python main.py fix https://github.com/o/r "crash on empty input"
    python main.py build "a CLI to-do manager with tests"
    python main.py resume <task_id>                  continue from shared memory
    python main.py memory <task_id>                  the shared memory, with provenance
    python main.py diff <task_id>                    the fix as a patch
    python main.py files <task_id> | state <task_id> | tasks

Without GOOGLE_API_KEY every run uses the offline mock model.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shlex
import sys
from pathlib import Path

try:
    from shared_memory.guardrails import GuardrailLog, check_repo_source, check_request
    from shared_memory.handoff import build_team, plan
    from shared_memory.protocol import DEMO_REQUEST, fix_objective, is_fix
    from shared_memory.workspace import clone_repo, diff_text, export_patch, task_dir, task_files
except ModuleNotFoundError as exc:  # usually: run outside the project's virtual environment
    activate = r".venv\Scripts\activate" if os.name == "nt" else "source .venv/bin/activate"
    sys.exit(
        f"Missing dependency: {exc.name}. You are probably not in this project's virtual environment.\n"
        f"From {Path(__file__).resolve().parent}:\n"
        f"  python -m venv .venv\n  {activate}\n  pip install -r requirements.txt\n  python main.py"
    )

DEFAULT_DB = "team.db"
URL = re.compile(r"https://[^\s,;)]+")


# -- understanding a typed task ------------------------------------------------


def parse_task(text: str) -> tuple[str, str | None, str]:
    """('fix', source, bug) when the text names a repository, else ('build', None, text)."""
    text = text.strip()
    match = URL.search(text) or re.search(
        r"""\bclone\s+(?:the\s+repo\s+|this\s+repo\s+)?("[^"]+"|'[^']+'|\S+)""", text, re.I)
    if not match:
        return "build", None, text
    source = match.group(0) if match.re is URL else match.group(1).strip("\"'")
    source = source.rstrip(".")
    bug = (text[: match.start()] + " " + text[match.end():]).strip()
    bug = re.sub(r"^(please\s+)?(clone|git clone)(\s+(this|the)\s+repo(sitory)?)?\s*", "", bug, flags=re.I)
    bug = re.sub(r"^[\s,:;-]*(and\s+(then\s+)?)?(fix|debug|solve)?(\s+(this|the)\s+bug)?[\s,:;-]*", "",
                 bug, flags=re.I)
    return "fix", source, bug.strip()


# -- printing ---------------------------------------------------------------------


def print_turn(result, log: GuardrailLog, seen: list[int], show_context: bool) -> None:
    p, r = result.package, result.report
    print(f"\nturn {result.turn}/{len(result.state.plan)}  {result.worker.id}  ({result.worker.model})")
    print(f"  task       {result.assigned_task}")
    print(f"  briefing   {p.estimated_tokens} of {p.budget} tokens, omitted: "
          f"{', '.join(p.omitted_sections) or 'none'}")
    print(f"  reconciled +{r.decisions_added} decisions, +{len(r.artifacts_created)} artifacts, "
          f"{len(r.artifacts_versioned)} versioned, +{len(r.issues_opened)} issues, "
          f"{len(r.rejected_resolutions)} fix claims kept open")
    for _role, kind, detail in log.events[seen[0]:]:
        print(f"  guardrail  {kind}: {detail}")
    seen[0] = len(log.events)
    for warning in r.warnings:
        print(f"  warning    {warning}")
    if show_context:
        print("  ---- briefing sent ----\n  " + p.rendered_text.replace("\n", "\n  "))


def print_summary(summary, store) -> None:
    state = store.load_state(summary.task_id)
    print(f"\n{summary.task_id}  {summary.status}  ({summary.turns}/{summary.steps} steps)")
    print(f"  agents used                 {', '.join(summary.workers_used)}")
    print(f"  raw conversation transfers  {summary.raw_conversation_transfers}")
    print(f"  peak briefing tokens        {summary.peak_package_tokens}")
    if is_fix(state.objective):
        patch = export_patch(summary.task_id)
        print(f"  patch                       {patch or 'no changes'}")
    else:
        print(f"  files in workspace          {', '.join(task_files(summary.task_id)) or 'none'}")
    print(f"  open issues                 {len(state.open_issues())}")
    for issue in state.open_issues():
        claimed = (f" (fix claimed by {issue.resolution_claimed_by}, unverified)"
                   if issue.resolution_claimed_by else "")
        print(f"    {issue.id} [{issue.severity}] {issue.description}{claimed}")
    print(f"\n  Shared memory: python main.py memory {summary.task_id}")
    if summary.status != "completed":
        print(f"  State is saved. Continue with: python main.py resume {summary.task_id}")


def print_memory(state) -> None:
    """The team's shared memory: what every agent's briefing is compiled from."""
    print(f"{state.task_id}  {state.status}  turn {state.turn}/{len(state.plan)}")
    print(f"objective: {state.objective}\n")
    sections = [
        ("decisions", [f"{d.decision}  (reason: {d.reason or '-'}; by {d.made_by}, turn {d.turn})"
                       for d in state.decisions]),
        ("artifacts", [f"{a.name} v{a.version}  (by {a.created_by}"
                       + (f", then {', '.join(a.modified_by)}" if a.modified_by else "")
                       + f"; {'verified' if a.verified else 'unverified'})" for a in state.artifacts]),
        ("issues", [f"{i.id} [{i.severity}] {i.status}: {i.description}  (opened by {i.opened_by}"
                    + (f"; fix claimed by {i.resolution_claimed_by}" if i.resolution_claimed_by else "")
                    + ")" for i in state.issues]),
        ("failed attempts", [f"{f.approach}: {f.reason}  (by {f.recorded_by})" for f in state.failed_attempts]),
        ("assumptions", [f"{a.text}  (by {a.recorded_by})" for a in state.assumptions]),
        ("history", [f"turn {h.turn} {h.worker_id}: {h.summary}" for h in state.history]),
    ]
    for title, rows in sections:
        print(f"{title} ({len(rows)})")
        for row in rows:
            print(f"  - {row}")
    if state.notes_from_previous:
        print(f"\nnotes from {state.previous_worker}: {state.notes_from_previous}")
    if state.next_action:
        print(f"next action: {state.next_action}")


# -- commands --------------------------------------------------------------------


def start(store, args, objective: str, source: str | None = None) -> int:
    problems = check_request(objective)
    if source is not None:
        reason = check_repo_source(source)
        problems += [reason] if reason else []
    if problems:
        print("Refused by guardrail: " + "; ".join(problems), file=sys.stderr)
        return 2
    team = make_team(store, args)
    task_id = team.create_task(objective, plan(objective)).task_id
    print(f"{task_id}: {objective}")
    if source is not None:
        print(f"  cloning {source} ...")
        clone_repo(source, task_id)
        print(f"  cloned into {task_dir(task_id)} ({len(task_files(task_id))} files)")
    print_summary(team.run(task_id, max_turns=args.stop_after), store)
    return 0


def make_team(store, args):
    mock = args.mock or (not args.real and not os.environ.get("GOOGLE_API_KEY"))
    if mock and not args.mock:
        print("No GOOGLE_API_KEY: using the offline mock model. "
              "Set it in .env (see .env.example) for live Gemini calls.")
    log, seen = GuardrailLog(), [0]
    return build_team(store, mock, log, budget=args.budget,
                      on_turn=lambda r: print_turn(r, log, seen, args.show_context))


def dispatch(args) -> int:
    from shared_memory.engine import SQLiteStore

    with SQLiteStore(args.db) as store:
        cmd = args.command
        if cmd == "build":
            return start(store, args, args.request or DEMO_REQUEST)
        if cmd == "fix":
            return start(store, args, fix_objective(args.repo, args.bug), source=args.repo)
        if cmd == "ask":
            kind, source, rest = parse_task(" ".join(args.text))
            if kind == "fix":
                if not rest:
                    print("Say what the bug is, e.g. 'clone <url> and fix: crash on empty input'.",
                          file=sys.stderr)
                    return 2
                return start(store, args, fix_objective(source, rest), source=source)
            return start(store, args, rest)
        if cmd == "tasks":
            rows = store.tasks()
            if not rows:
                print("No tasks yet.")
            for row in rows:
                kind = "fix  " if is_fix(row["objective"]) else "build"
                print(f"{row['task_id']}  {kind}  {row['status']:<9}  {row['turn']}/{row['steps']}  "
                      f"{row['objective'][:70]}")
            return 0

        task_id = store.resolve(args.task_id)
        if cmd == "resume":
            state = store.load_state(task_id)
            print(f"{task_id}: resuming at step {state.turn + 1} of {len(state.plan)}")
            print_summary(make_team(store, args).run(task_id, max_turns=args.stop_after), store)
        elif cmd == "memory":
            print_memory(store.load_state(task_id))
        elif cmd == "state":
            print(json.dumps(store.load_state(task_id).model_dump(), indent=2))
        elif cmd == "diff":
            print(diff_text(task_id) or "(no changes, or not a cloned repository)")
        elif cmd == "files":
            for name in task_files(task_id):
                print(f"===== {name}")
                print((task_dir(task_id) / name).read_text(encoding="utf-8", errors="replace"))
        return 0


def _options(parser: argparse.ArgumentParser, defaults: bool) -> argparse.ArgumentParser:
    # Subcommands repeat these options with SUPPRESS defaults: otherwise argparse
    # re-applies their defaults and `--db x tasks` silently reads the default db.
    d = (lambda value: value) if defaults else (lambda _value: argparse.SUPPRESS)
    parser.add_argument("--db", default=d(DEFAULT_DB), help=f"shared-memory SQLite file (default {DEFAULT_DB})")
    parser.add_argument("--mock", action="store_true", default=d(False), help="force the offline mock model")
    parser.add_argument("--real", action="store_true", default=d(False), help="force live Gemini calls")
    parser.add_argument("--budget", type=int, default=d(1200), help="token budget per briefing")
    parser.add_argument("--stop-after", type=int, metavar="N", default=d(None), help="stop after N agent turns")
    parser.add_argument("--show-context", action="store_true", default=d(False), help="print every briefing sent")
    return parser


def build_parser() -> argparse.ArgumentParser:
    common = _options(argparse.ArgumentParser(add_help=False), defaults=False)

    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="Architect, Junior and Senior agents on Google ADK with shared memory. "
                    "Run with no command for the interactive CLI.")
    _options(parser, defaults=True)
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("ask", parents=[common], help="a task in plain words (clone <repo> and fix <bug>, or build ...)")
    p.add_argument("text", nargs="+")
    p = sub.add_parser("fix", parents=[common], help="clone a repository and fix a bug")
    p.add_argument("repo", help="https:// URL or local directory")
    p.add_argument("bug", help="what is wrong")
    p = sub.add_parser("build", parents=[common], help="build something new from a request")
    p.add_argument("request", nargs="?", help="what to build (default: the demo request)")
    for name, text in (("resume", "continue a saved task"), ("memory", "show the shared memory"),
                       ("diff", "show the fix as a patch"), ("files", "print the task's files"),
                       ("state", "shared memory as JSON")):
        p = sub.add_parser(name, parents=[common], help=text)
        p.add_argument("task_id", help="task id (any unambiguous prefix)")
    sub.add_parser("tasks", parents=[common], help="list tasks")
    return parser


HELP = """Type a task, or a command:
  clone https://github.com/owner/repo and fix: <what is wrong>
  build <what to make>
  tasks | memory <id> | diff <id> | files <id> | resume <id> | state <id>
  help | quit"""


def interactive(parser: argparse.ArgumentParser, base: list[str]) -> int:
    print("Monarch: Architect, Junior and Senior agents on Google ADK, sharing context "
          "through Monarch Memory (the context-orchestration-engine).")
    print(HELP)
    while True:
        try:
            line = input("\nteam> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        word = line.split()[0].lower()
        if word in {"quit", "exit", "q"}:
            return 0
        if word in {"help", "?"}:
            print(HELP)
            continue
        if word in {"tasks", "memory", "diff", "files", "resume", "state", "fix", "build", "ask"}:
            # Non-POSIX splitting keeps Windows paths intact but leaves the quotes on.
            argv = [t[1:-1] if len(t) > 1 and t[0] == t[-1] and t[0] in "\"'" else t
                    for t in shlex.split(line, posix=False)]
        else:
            argv = ["ask", line]
        try:
            run(parser.parse_args(argv + base))
        except SystemExit:
            pass  # argparse already printed the problem; stay in the loop


def run(args) -> int:
    try:
        return dispatch(args)
    except KeyError as exc:
        print(exc.args[0] if exc.args else exc, file=sys.stderr)
        return 1
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    logging.getLogger("google_adk").setLevel(logging.ERROR)
    try:  # show progress as it happens, even when output goes to a file
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):  # pragma: no cover - replaced streams
        pass
    try:
        from dotenv import load_dotenv

        load_dotenv(Path.cwd() / ".env")
    except ImportError:  # pragma: no cover - listed in requirements.txt
        pass
    argv = sys.argv[1:] if argv is None else argv
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        return interactive(parser, argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
