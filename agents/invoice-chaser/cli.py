"""Invoice Chaser owner CLI.

Owner-only actions (imports, confirming matches, approving / sending reminders,
disputes) live here. The agent can only propose; you decide.

    python cli.py init --sample          create the ledger and load the demo data
    python cli.py status                 who owes what, ranked
    python cli.py chase                  run the agent: match payments + draft reminders
    python cli.py ask "who owes me the most?"
    python cli.py matches                confirm / reject uncertain payment matches
    python cli.py review                 approve / edit / skip reminder drafts
    python cli.py sent 3                 record that you sent reminder 3
    python cli.py hold INV-2026-004 disputed --reason "menu not final"
    python cli.py audit --invoice INV-2026-004
"""

import argparse
import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_DIR / ".env")
except ImportError:  # dotenv ships with google-adk; the ledger commands work without it
    pass

from ledger import Ledger, LedgerConfig, LedgerError  # noqa: E402
from ledger.config import db_path  # noqa: E402

TONE_NAMES = {0: "heads-up", 1: "gentle nudge", 2: "firm reminder", 3: "final notice"}
REASON_TEXT = {
    "INVOICE_PAID": "already paid",
    "INVOICE_DISPUTED": "disputed",
    "INVOICE_WRITTEN_OFF": "written off",
    "NOT_DUE_YET": "not due yet",
    "TOO_OLD_CONSIDER_WRITE_OFF": "over 180 days old, consider writing off",
    "PENDING_REMINDER_EXISTS": "a draft is already waiting for review",
    "COOLDOWN": "reminded recently",
    "TONE_ABOVE_CLIENT_CAP": "tone above this client's limit",
}


def ledger() -> Ledger:
    return Ledger(db_path(), LedgerConfig.from_env(), actor="owner")


def ask_choice(prompt: str, choices: str) -> str:
    while True:
        answer = input(prompt).strip().lower()[:1]
        if answer in choices:
            return answer
        print(f"  please type one of: {', '.join(choices)}")


def edit_text(initial: str) -> str:
    editor = os.getenv("EDITOR")
    if editor:
        with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as f:
            f.write(initial)
            path = f.name
        subprocess.call([editor, path])
        text = Path(path).read_text(encoding="utf-8").strip()
        os.unlink(path)
        return text
    print("  Type the new text. Finish with a single '.' on its own line.")
    lines = []
    while (line := input()) != ".":
        lines.append(line)
    return "\n".join(lines).strip()


# ---------------------------------------------------------------- commands

def cmd_init(args):
    path = db_path()
    if path.exists() and not args.force:
        print(f"Ledger already exists at {path}. Use --force to start over (this deletes it).")
        return 1
    if path.exists():
        path.unlink()
    led = ledger()
    print(f"Created ledger at {path}")
    if args.sample:
        sample = PROJECT_DIR / "sample_data"
        print(" clients:", led.import_clients(str(sample / "clients.csv")))
        print(" invoices:", led.import_invoices(str(sample / "invoices.csv")))
        print(" payments:", led.import_payments(str(sample / "bank_statement.csv")))
        if not os.getenv("INVOICE_CHASER_TODAY"):
            print("\nTip: the sample data is written for 24 Oct 2026. Set "
                  "INVOICE_CHASER_TODAY=2026-10-24 in .env to reproduce the README examples.")
    return 0


def cmd_import(args):
    method = {"clients": "import_clients", "invoices": "import_invoices",
              "payments": "import_payments"}[args.kind]
    print(getattr(ledger(), method)(args.path))
    return 0


def cmd_status(args):
    led = ledger()
    chase = led.get_chase_list()
    print(f"As of {chase['as_of']}\n")
    if not chase["items"]:
        print("Nothing due or overdue.")
    else:
        print(f"{'Invoice':<14}{'Client':<26}{'Outstanding':>13}  {'Overdue':>8}  {'Tone':<15}Next step")
        for i in chase["items"]:
            overdue = f"{i['days_overdue']}d" if i["days_overdue"] > 0 else f"due {-i['days_overdue']}d"
            nxt = "can draft reminder" if i["can_queue_reminder"] else \
                ", ".join(REASON_TEXT.get(r, r) for r in i["policy_reasons"])
            print(f"{i['invoice_id']:<14}{i['client_name'][:25]:<26}{i['outstanding']:>13}  "
                  f"{overdue:>8}  {TONE_NAMES[i['recommended_tone']]:<15}{nxt}")
    pending = led.list_pending_matches()["proposals"]
    queued = led.list_reminders("QUEUED")["reminders"]
    unmatched = led.list_unmatched_payments()["payments"]
    print(f"\n{len(unmatched)} unmatched payment(s) · {len(pending)} match(es) to confirm "
          f"(cli.py matches) · {len(queued)} draft(s) to review (cli.py review)")
    return 0


def cmd_matches(args):
    led = ledger()
    if args.action:
        method = led.confirm_match if args.action == "confirm" else led.reject_match
        print(method(args.proposal_id))
        return 0
    proposals = led.list_pending_matches()["proposals"]
    if not proposals:
        print("No matches waiting for confirmation.")
        return 0
    for p in proposals:
        print(f"\n#{p['proposal_id']}  {p['date']}  {p['amount']}  \"{p['narration']}\"")
        print(f"   → {', '.join(p['invoice_ids'])}   ({p['signal']}, name confidence "
              f"{p['name_confidence']:.2f})")
        print(f"   agent's reason: {p['reason']}")
        for inv_id in p["invoice_ids"]:
            inv = led.get_invoice(inv_id)["invoice"]
            print(f"   {inv_id}: {inv['client_name']}, outstanding {inv['outstanding']}")
        if p["ambiguous_with"]:
            print(f"   ⚠ the amount also fits: {', '.join(p['ambiguous_with'])}")
        choice = ask_choice("   [c]onfirm  [r]eject  [s]kip > ", "crs")
        try:
            if choice == "c":
                print("  ", led.confirm_match(p["proposal_id"]))
            elif choice == "r":
                print("  ", led.reject_match(p["proposal_id"]))
        except LedgerError as e:
            print(f"   ✗ {e.code}: {e.message}")
    return 0


def cmd_review(args):
    led = ledger()
    drafts = led.list_reminders("QUEUED")["reminders"]
    if not drafts:
        print("No drafts to review. Run `python cli.py chase` first.")
        return 0
    for d in drafts:
        print("\n" + "─" * 72)
        print(f"Draft #{d['reminder_id']} · {d['invoice_id']} · {d['client_name']} <{d['email']}>")
        print(f"Tone: {TONE_NAMES[d['tone_level']]} · Language: {d['language']}")
        print(f"\nSubject: {d['subject']}\n\n{d['body']}\n")
        choice = ask_choice("[a]pprove  [e]dit  [s]kip  [n]ext > ", "aesn")
        try:
            if choice == "a":
                led.approve_reminder(d["reminder_id"])
            elif choice == "e":
                print("Edit subject (leave empty to keep):")
                subject = input("> ").strip() or d["subject"]
                body = edit_text(d["body"]) or d["body"]
                led.approve_reminder(d["reminder_id"], subject=subject, body=body)
            elif choice == "s":
                led.skip_reminder(d["reminder_id"])
                print("Skipped.")
                continue
            else:
                continue
            print(f"Approved. Copy it into your email client, send it, then run: "
                  f"python cli.py sent {d['reminder_id']}")
        except LedgerError as e:
            print(f"✗ {e.code}: {e.message}")
    return 0


def cmd_sent(args):
    print(ledger().mark_sent(args.reminder_id, args.on))
    return 0


def cmd_hold(args):
    hold = {"disputed": "DISPUTED", "written_off": "WRITTEN_OFF", "clear": None}[args.hold]
    print(ledger().set_invoice_hold(args.invoice_id, hold, args.reason))
    return 0


def cmd_audit(args):
    for e in reversed(ledger().get_audit_log(entity_id=args.invoice, run_id=args.run,
                                             limit=args.limit)["events"]):
        print(f"{e['ts']}  {e['actor']:<6} {e['action']:<18} {e['entity']} {e['entity_id']}  "
              f"{e['details'] or ''}")
    return 0


def run_agent(message: str) -> int:
    if not os.getenv("GOOGLE_API_KEY") and os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").upper() != "TRUE":
        print("GOOGLE_API_KEY is not set. Copy .env.example to .env and add your key from "
              "https://aistudio.google.com/apikey")
        return 1
    if not db_path().exists():
        print("No ledger yet. Run: python cli.py init --sample")
        return 1
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    from invoice_chaser.agent import root_agent

    async def go():
        runner = InMemoryRunner(agent=root_agent, app_name="invoice_chaser")
        session = await runner.session_service.create_session(app_name="invoice_chaser",
                                                              user_id="owner")
        final = None
        try:
            async for event in runner.run_async(
                    user_id="owner", session_id=session.id,
                    new_message=types.Content(role="user", parts=[types.Part.from_text(text=message)])):
                for part in (event.content.parts if event.content else None) or []:
                    if part.function_call:
                        print(f"  · {event.author} → {part.function_call.name}")
                    elif part.text and event.author == "invoice_chaser" and not event.partial:
                        final = part.text
        finally:
            await runner.close()
        return final

    print(f"\n{asyncio.run(go()) or '(no reply)'}")
    return 0


def cmd_chase(args):
    return run_agent("Run today's chase.")


def cmd_ask(args):
    return run_agent(" ".join(args.question))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="cli.py", description="Invoice Chaser owner CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create the ledger database")
    p.add_argument("--sample", action="store_true", help="load the demo data")
    p.add_argument("--force", action="store_true", help="delete an existing ledger first")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("import", help="import a CSV file")
    p.add_argument("kind", choices=["clients", "invoices", "payments"])
    p.add_argument("path")
    p.set_defaults(func=cmd_import)

    sub.add_parser("status", help="ranked chase list and pending work").set_defaults(func=cmd_status)
    sub.add_parser("chase", help="run the agent (needs GOOGLE_API_KEY)").set_defaults(func=cmd_chase)

    p = sub.add_parser("ask", help="ask the agent a question (needs GOOGLE_API_KEY)")
    p.add_argument("question", nargs="+")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("matches", help="confirm or reject uncertain payment matches")
    p.add_argument("action", nargs="?", choices=["confirm", "reject"])
    p.add_argument("proposal_id", nargs="?", type=int)
    p.set_defaults(func=cmd_matches)

    sub.add_parser("review", help="approve, edit or skip reminder drafts").set_defaults(func=cmd_review)

    p = sub.add_parser("sent", help="record that you sent an approved reminder")
    p.add_argument("reminder_id", type=int)
    p.add_argument("--on", help="date sent (YYYY-MM-DD), default today")
    p.set_defaults(func=cmd_sent)

    p = sub.add_parser("hold", help="dispute, write off, or clear an invoice")
    p.add_argument("invoice_id")
    p.add_argument("hold", choices=["disputed", "written_off", "clear"])
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_hold)

    p = sub.add_parser("audit", help="show the audit trail")
    p.add_argument("--invoice")
    p.add_argument("--run")
    p.add_argument("--limit", type=int, default=30)
    p.set_defaults(func=cmd_audit)

    args = parser.parse_args(argv)
    if args.command == "matches" and args.action and args.proposal_id is None:
        parser.error("matches confirm/reject needs a proposal id")
    try:
        return args.func(args)
    except LedgerError as e:
        print(f"✗ {e.code}: {e.message}")
        for detail in e.details.get("errors", []) + e.details.get("problems", []):
            print(f"  - {detail}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
