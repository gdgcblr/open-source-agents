"""Command line interface. Exit codes: 0 no change, 1 behavior changed, 2 usage/policy error, 3 incomplete."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import anyio

from . import __version__
from .diff import Difference, compare, incomplete
from .errors import PolicyViolation, UsageError
from .fixture import Fixture, load_fixture
from .redact import sanitize_text
from .runner import CallRecord, run_server

EXIT_OK, EXIT_CHANGED, EXIT_USAGE, EXIT_INCOMPLETE = 0, 1, 2, 3


def _command_line(spec) -> str:
    return sanitize_text(" ".join([spec.command, *spec.args]))


def _describe(fixture: Fixture) -> str:
    lines = [f"fixture: {fixture.path}"]
    for label, spec in fixture.servers.items():
        lines.append(f"  {label}: {_command_line(spec)}" + (f"   (cwd: {spec.cwd})" if spec.cwd else ""))
        if spec.env_passthrough:
            lines.append(f"       passes through env: {', '.join(spec.env_passthrough)}")
    lines.append(f"  calls: {', '.join(f'{c.id}->{c.tool}' for c in fixture.calls)}")
    return "\n".join(lines)


def _confirm(fixture: Fixture, assume_yes: bool) -> None:
    """The fixture names programs to execute. Show them and require explicit consent."""
    print(_describe(fixture), file=sys.stderr)
    print("\nThese commands will be EXECUTED on this machine (no sandbox).", file=sys.stderr)
    if assume_yes:
        return
    if not sys.stdin.isatty():
        raise PolicyViolation("non-interactive session: re-run with --yes to confirm execution")
    if input("Proceed? [y/N] ").strip().lower() not in {"y", "yes"}:
        raise PolicyViolation("aborted by user")


def _render_text(fixture: Fixture, old: list[CallRecord], new: list[CallRecord], diffs: list[Difference], skipped: list[str]) -> str:
    changed = {d.id: d for d in diffs}
    out: list[str] = []
    for a, b in zip(old, new, strict=True):
        if a.id in changed:
            out.append(f"[~] {a.id}  ({a.tool})  CHANGED  old={a.status} new={b.status}")
            out.extend(f"      {line}" for line in changed[a.id].diff_lines)
        elif a.id in skipped:
            out.append(f"[!] {a.id}  ({a.tool})  NOT EXECUTED  old={a.status}:{a.detail} new={b.status}:{b.detail}")
        else:
            out.append(f"[=] {a.id}  ({a.tool})  identical  ({a.status})")
    out.append(f"\n{len(old)} call(s): {len(diffs)} changed, {len(skipped)} not executed")
    return sanitize_text("\n".join(out))


def _write_report(path: Path, payload: dict, force: bool) -> None:
    if path.is_symlink():
        raise PolicyViolation(f"refusing to write through symlink: {path}")
    if not path.parent.is_dir():
        raise PolicyViolation(f"output directory does not exist: {path.parent}")
    try:
        with open(path, "w" if force else "x", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError as exc:
        raise PolicyViolation(f"{path} already exists; use --force to overwrite") from exc


def _cmd_check(args: argparse.Namespace) -> int:
    fixture = load_fixture(args.fixture)
    print(_describe(fixture))
    print("\nfixture is valid; nothing was executed.")
    return EXIT_OK


def _cmd_diff(args: argparse.Namespace) -> int:
    fixture = load_fixture(args.fixture)
    _confirm(fixture, args.yes)
    allow = frozenset(args.allow_secret_env or [])

    async def go() -> tuple[list[CallRecord], list[CallRecord]]:
        old = await run_server(fixture.servers["old"], fixture.calls, fixture.limits, os.environ, allow)
        new = await run_server(fixture.servers["new"], fixture.calls, fixture.limits, os.environ, allow)
        return old, new

    old, new = anyio.run(go)
    diffs = compare(old, new)
    changed_ids = {d.id for d in diffs}
    skipped = [i for i in incomplete(old, new) if i not in changed_ids]
    print(_render_text(fixture, old, new, diffs, skipped))
    if args.json_out:
        payload = {
            "tool_version": __version__,
            "changed": [d.id for d in diffs],
            "not_executed": skipped,
            "old": [r.__dict__ for r in old],
            "new": [r.__dict__ for r in new],
        }
        _write_report(Path(args.json_out), payload, args.force)
    if diffs:
        return EXIT_CHANGED
    return EXIT_INCOMPLETE if skipped else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mcp-behavior-diff", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="validate a fixture without executing anything")
    check.add_argument("fixture")
    check.set_defaults(func=_cmd_check)
    diff = sub.add_parser("diff", help="run the fixture's calls against old and new servers and compare")
    diff.add_argument("fixture")
    diff.add_argument("--yes", action="store_true", help="confirm execution of the fixture's commands")
    diff.add_argument("--allow-secret-env", action="append", metavar="NAME", help="allow a secret-looking env var to be passed through")
    diff.add_argument("--json-out", metavar="PATH", help="write a JSON report (refuses to overwrite without --force)")
    diff.add_argument("--force", action="store_true", help="overwrite --json-out if it exists")
    diff.set_defaults(func=_cmd_diff)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except UsageError as exc:
        print(f"error: {sanitize_text(str(exc))}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
