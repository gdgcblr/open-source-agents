"""Command line interface: aran scan | redact | restore | audit | profiles | mcp."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from aran import audit, engine, profiles
from aran.local_llm import LocalModelError

out = Console()
err = Console(stderr=True)

_ACTION_STYLE = {"mask": "green", "age_band": "cyan", "keep": "yellow"}


def _scan(args: argparse.Namespace) -> None:
    session = args.session
    for file in args.files:
        with err.status(f"Reading {file} locally..."):
            r = engine.redact_document(file, args.profile, session, use_llm=not args.no_llm, channel="cli")
        session = r.session_id
        table = Table(title=f"{file}  [dim]({r.kind}, profile={r.profile})[/]", title_justify="left")
        for col in ("Type", "Value (hint)", "Action", "Becomes", "Checksum", "Detector"):
            table.add_column(col)
        for f in r.findings:
            table.add_row(
                f["type"],
                f["preview"],
                f"[{_ACTION_STYLE[f['action']]}]{f['action']}[/]",
                escape(f["replacement"]) if f["replacement"] else "[dim](kept)[/]",
                "[green]valid[/]" if f["checksum_valid"] else "[dim]-[/]",
                f["detector"],
            )
        out.print(table)
    s = audit.summarise(audit.read(session))
    out.print(Panel(
        f"[bold]{s['pii_found']}[/] personal data items found in {s['documents']} document(s)\n"
        f"[bold green]{s['pii_protected']}[/] hidden or generalised before any cloud call\n"
        f"[bold]0[/] raw values sent to the cloud      session: [cyan]{session}[/]",
        title="Aran", border_style="green",
    ))


def _redact(args: argparse.Namespace) -> None:
    r = engine.redact_document(args.file, args.profile, args.session, use_llm=not args.no_llm, channel="cli")
    if args.output:
        Path(args.output).write_text(r.redacted)
    else:
        sys.stdout.write(r.redacted + "\n")
    err.print(f"[green]session[/] {r.session_id}  [dim]({r.total_found} items hidden/handled)[/]")


def _restore(args: argparse.Namespace) -> None:
    text = Path(args.file).read_text() if args.file and args.file != "-" else sys.stdin.read()
    sys.stdout.write(engine.restore(text, args.session))


def _audit(args: argparse.Namespace) -> None:
    entries = audit.read(args.session)
    table = Table(title="Aran audit log (no personal data is stored here)", title_justify="left")
    for col in ("Time (UTC)", "Session", "Kind", "Profile", "Channel", "Found", "Hidden", "Raw sent"):
        table.add_column(col)
    for e in entries[-args.limit:]:
        table.add_row(
            e["ts"][:19].replace("T", " "), e["session"], e["kind"], e["profile"], e["channel"],
            str(sum(e["found"].values())),
            str(sum(e["masked"].values()) + sum(e["generalised"].values())),
            str(e["raw_values_sent"]),
        )
    out.print(table)
    s = audit.summarise(entries)
    by_type = ", ".join(f"{k} {v}" for k, v in s["by_type"].items()) or "none"
    out.print(f"[bold]{s['pii_found']}[/] found, [bold green]{s['pii_protected']}[/] protected, "
              f"[bold]0[/] raw values sent.  By type: {by_type}")


def _profiles(_: argparse.Namespace) -> None:
    for name in profiles.available():
        p = profiles.load(name)
        out.print(f"[bold]{p.name}[/]: {p.description}")
        for kind, action in p.actions.items():
            out.print(f"   {kind:<15} [{_ACTION_STYLE[action]}]{action}[/]")


def _mcp(_: argparse.Namespace) -> None:
    from aran.mcp_server import main as run

    run()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aran", description="Aran (அரண்): hide Indian PII locally before any cloud LLM call.")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--profile", default="kyc", choices=profiles.available())
        p.add_argument("--session", help="Reuse a session so tokens stay consistent across documents")
        p.add_argument("--no-llm", action="store_true", help="Rules only; skip the local model (no names/addresses, no scans)")

    p = sub.add_parser("scan", help="Show what personal data a document contains and how it would be handled")
    p.add_argument("files", nargs="+")
    common(p)
    p.set_defaults(func=_scan)

    p = sub.add_parser("redact", help="Print the redacted document (safe to send to a cloud LLM)")
    p.add_argument("file")
    p.add_argument("-o", "--output")
    common(p)
    p.set_defaults(func=_redact)

    p = sub.add_parser("restore", help="Put real values back into a model's answer (local only)")
    p.add_argument("--session", required=True)
    p.add_argument("file", nargs="?", default="-")
    p.set_defaults(func=_restore)

    p = sub.add_parser("audit", help="Show the audit log")
    p.add_argument("--session")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=_audit)

    sub.add_parser("profiles", help="List redaction profiles").set_defaults(func=_profiles)
    sub.add_parser("mcp", help="Run the MCP server on stdio").set_defaults(func=_mcp)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (LocalModelError, ValueError, FileNotFoundError) as e:
        err.print(f"[red]error:[/] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
