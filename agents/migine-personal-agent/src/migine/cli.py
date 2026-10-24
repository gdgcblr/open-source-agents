import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .adapters import adapter_for, serve_connector
from .config import Settings
from .demo import load_demo
from .finance import month_key, monthly_summary
from .ollama import Ollama, search
from .safety import apply_request, propose
from .storage import Store


def output(value):
    print(json.dumps(value, indent=2, ensure_ascii=True, default=str))


def parser():
    p = argparse.ArgumentParser(description="Migine: a local Mac personal agent.")
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("demo", "summary"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--month", type=month_key)
    cmd = sub.add_parser("brief")
    cmd.add_argument("--date", type=date.fromisoformat)
    cmd.add_argument("--calendar", action="store_true")
    cmd = sub.add_parser("sync")
    cmd.add_argument("--since", type=date.fromisoformat, required=True)
    cmd.add_argument("--limit", type=int, default=50)
    cmd.add_argument("--offset", type=int, default=0)
    sub.add_parser("extract")
    cmd = sub.add_parser("review")
    cmd.add_argument("id", nargs="?")
    cmd.add_argument("decision", nargs="?", choices=["accept", "reject"])
    cmd = sub.add_parser("search")
    cmd.add_argument("query")
    cmd.add_argument("--semantic", action="store_true")
    sub.add_parser("index")
    cmd = sub.add_parser("remember")
    cmd.add_argument("key")
    cmd.add_argument("value")
    sub.add_parser("memories")
    cmd = sub.add_parser("forget")
    cmd.add_argument("key")
    cmd.add_argument("--source", action="store_true")
    cmd = sub.add_parser("calendar")
    cmd.add_argument("--days", type=int, default=14)
    cmd = sub.add_parser("contacts")
    cmd.add_argument("query")
    cmd = sub.add_parser("propose")
    cmd.add_argument("operation")
    cmd.add_argument("payload", help="JSON object")
    cmd = sub.add_parser("apply")
    cmd.add_argument("id")
    cmd = sub.add_parser("chat")
    cmd.add_argument("prompt")
    cmd.add_argument("--session", default="default")
    cmd = sub.add_parser("connector")
    cmd.add_argument("--bind", default="127.0.0.1")
    cmd.add_argument("--port", type=int, default=8765)
    cmd.add_argument("--token-file", type=Path, required=True)
    sub.add_parser("doctor")
    sub.add_parser("export")
    return p


def execute(args, settings):
    if args.command == "connector":
        serve_connector(args.token_file, args.bind, args.port)
        return
    store = Store(settings.data_dir)
    adapter = adapter_for(settings)
    model = Ollama(settings)
    today = datetime.now(ZoneInfo(settings.timezone)).date()
    month = getattr(args, "month", None) or today.strftime("%Y-%m")
    match args.command:
        case "demo":
            if store.path.parent.name != "demo":
                raise ValueError("Set MIGINE_DATA_DIR to a separate directory named demo.")
            return load_demo(store, month)
        case "summary":
            return monthly_summary(store.records(), month) | {"scan": store.coverage()}
        case "brief":
            day = args.date or today
            records = [r for r in store.records() if r["data"]["occurred_on"] <= day.isoformat()]
            report = monthly_summary(records, day.strftime("%Y-%m"))
            report["scan"] = store.coverage()
            with store.connect() as db:
                notice = db.execute(
                    "SELECT value FROM preferences WHERE key='bill_notice_days'"
                ).fetchone()
            notice_days = max(0, min(90, int(notice["value"]))) if notice else 3
            cutoff = (day + timedelta(days=notice_days)).isoformat()
            due_months = {r["data"]["due_on"][:7] for r in records if r["data"]["kind"] == "bill"}
            all_bills = [
                b for m in sorted(due_months) for b in monthly_summary(records, m)["bills"]
            ]
            report["attention"] = [
                b
                for b in all_bills
                if b["status"] != "confirmed_by_email" and b["due_on"] <= cutoff
            ]
            report["bill_notice_days"] = notice_days
            report["as_of"] = day.isoformat()
            report["calendar"] = (
                adapter.call("calendar.read", {"days": 14})
                if args.calendar
                else "Not requested; use --calendar."
            )
            return report
        case "sync":
            scan = adapter.call(
                "mail.read",
                {"since": args.since.isoformat(), "limit": args.limit, "offset": args.offset},
            )
            sources = scan["sources"]
            for source in sources:
                store.add_source(source)
            detail = (
                f"Inbox positions {args.offset} to {args.offset + args.limit - 1}; "
                f"attempted {scan['scanned_positions']}; "
                f"cached {len(sources)}; partial={scan['partial']}; "
                "source text capped at 16000 characters"
            )
            with store.connect() as db:
                db.execute(
                    "INSERT OR REPLACE INTO sync_state VALUES(?,?,?)",
                    ("mail", datetime.now(UTC).isoformat(), detail),
                )
            return {
                "cached": len(sources),
                "coverage": detail,
                "skipped_batches": scan["skipped_batches"],
                "scanned_positions": scan["scanned_positions"],
                "next": "Run extract, then review each candidate.",
            }
        case "extract":
            with store.connect() as db:
                sources = [dict(r) for r in db.execute("SELECT * FROM sources LIMIT 200")]
            count = 0
            for source in sources:
                for record in model.extract(
                    {k: source[k] for k in ("id", "title", "body", "received")}
                ):
                    store.add_record(source["id"], record)
                    count += 1
            return {"candidates": count, "review": "Run migine review before using totals."}
        case "review":
            if not args.id:
                return store.records("pending")
            if not args.decision:
                raise ValueError("Specify accept or reject after the record ID.")
            store.review(args.id, args.decision == "accept")
            return {"reviewed": args.id, "decision": args.decision}
        case "search":
            return search(store, args.query, model if args.semantic else None)
        case "index":
            with store.connect() as db:
                sources = [dict(r) for r in db.execute("SELECT * FROM sources")]
            for source in sources:
                vector = model.embed(source["title"] + "\n" + source["body"])
                with store.connect() as db:
                    db.execute(
                        "INSERT OR REPLACE INTO vectors VALUES(?,?,?)",
                        (source["id"], settings.embedding_model, json.dumps(vector)),
                    )
            return {"indexed": len(sources), "model": settings.embedding_model}
        case "remember":
            store.remember(args.key, args.value)
            return {"saved": args.key}
        case "memories":
            with store.connect() as db:
                return [dict(r) for r in db.execute("SELECT * FROM preferences")]
        case "forget":
            if args.source:
                store.forget_source(args.key)
            else:
                with store.connect() as db:
                    db.execute("DELETE FROM preferences WHERE key=?", (args.key,))
            return {"deleted": args.key}
        case "calendar":
            return adapter.call("calendar.read", {"days": args.days})
        case "contacts":
            return adapter.call("contacts.search", {"query": args.query})
        case "propose":
            return propose(store, args.operation, json.loads(args.payload))
        case "apply":
            return apply_request(store, adapter, args.id)
        case "chat":
            return asyncio.run(
                __import__("migine.agent", fromlist=["chat"]).chat(
                    settings, store, adapter, args.prompt, args.session
                )
            )
        case "doctor":
            names = [m["name"] for m in model.tags()["models"]]
            return {
                "models": names,
                "chat_model_installed": settings.chat_model in names,
                "embedding_model_installed": settings.embedding_model + ":latest" in names,
                "mac_connector": settings.connector_url or "native",
                "permissions": "Run calendar, contacts, and sync to test permissions.",
            }
        case "export":
            with store.connect() as db:
                return {
                    "preferences": [dict(r) for r in db.execute("SELECT * FROM preferences")],
                    "records": store.records(),
                    "coverage": [dict(r) for r in db.execute("SELECT * FROM sync_state")],
                }


def main():
    os.umask(0o077)
    os.environ["LITELLM_TELEMETRY"] = "False"
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    os.environ["OTEL_SDK_DISABLED"] = "true"
    args = parser().parse_args()
    try:
        value = execute(args, Settings.load())
        if value is not None:
            output(value)
    except Exception as error:  # noqa: BLE001 -- CLI boundary redacts private error content.
        # Avoid logging exception details that could include personal content or tokens.
        print(
            f"Failed: {type(error).__name__}. Check configuration, app permissions, "
            "model availability, and request arguments.",
            file=sys.stderr,
        )
        return sys.exit(1)
