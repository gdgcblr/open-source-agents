"""Command-line interface: `mcp-poison-scan scan` and `mcp-poison-scan pin`."""

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

from . import __version__
from .client import McpClientError, list_tools, list_tools_http
from .loader import LoadError, load_config, load_tools_file, server_spec
from .lockfile import build_lock, diff_lock
from .report import exit_code, render_json, render_text
from .rules import SEVERITIES, scan_servers


def _add_source_args(parser):
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--server", metavar="CMD", help="command that starts a stdio MCP server (runs it!)")
    source.add_argument("--url", help="URL of a remote (Streamable HTTP) MCP server")
    source.add_argument("--file", metavar="PATH", help="JSON file with tools (tools/list output); nothing is executed")
    source.add_argument("--config", metavar="PATH", help="MCP client config (VS Code, Claude Code, Claude Desktop, Cursor, Windsurf)")
    parser.add_argument("--name", help="server name used in reports and lockfiles (default: derived from source)")
    parser.add_argument("--header", action="append", default=[], metavar="'NAME: VALUE'",
                        help="with --url: HTTP header to send, e.g. 'Authorization: Bearer $TOKEN' (repeatable)")
    parser.add_argument("--launch", action="store_true",
                        help="with --config: start stdio servers and connect to remote servers to fetch their tools")
    parser.add_argument("--timeout", type=float, default=15, help="seconds to wait for each server (default: 15)")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="mcp-poison-scan",
        description="Scan MCP server tool definitions for tool poisoning and rug-pulls.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="scan tools and report findings")
    _add_source_args(scan)
    scan.add_argument("--lock", metavar="PATH", help="lockfile from `pin`; report tools that changed")
    scan.add_argument("--format", choices=("text", "json"), default="text")
    scan.add_argument("--fail-on", choices=SEVERITIES, default="medium",
                      help="exit with code 1 if a finding is at or above this severity (default: medium)")
    scan.add_argument("--max-description", type=int, default=1000, metavar="N",
                      help="flag descriptions longer than N characters (default: 1000)")

    pin = sub.add_parser("pin", help="write a lockfile with a hash of every tool")
    _add_source_args(pin)
    pin.add_argument("--out", default="mcp-tools.lock.json", metavar="PATH")
    return parser


class UsageError(Exception):
    pass


def parse_headers(values):
    headers = {}
    for value in values:
        name, sep, content = value.partition(":")
        if not sep or not name.strip() or " " in name.strip():
            raise UsageError(f"invalid --header {value!r}; expected 'Name: value'")
        headers[name.strip()] = content.strip()
    return headers


def collect(args):
    """Return ({server: tools}, notes, failed) where failed counts servers that could not be scanned."""
    if args.file:
        return {args.name or Path(args.file).stem: load_tools_file(args.file)}, [], 0
    if args.server:
        return {args.name or args.server: list_tools(args.server, timeout=args.timeout)}, [], 0
    if args.url:
        name = args.name or urllib.parse.urlparse(args.url).netloc or args.url
        return {name: list_tools_http(args.url, parse_headers(args.header), timeout=args.timeout)}, [], 0

    servers, notes, failed = {}, [], 0
    for name, spec in load_config(args.config).items():
        try:
            kind, target, extra = server_spec(spec)
            if kind == "unsupported":
                notes.append(f"Skipped {name}: {target}")
                if args.launch:
                    failed += 1
            elif not args.launch:
                shown = " ".join(target) if kind == "stdio" else target
                notes.append(f"Found {name} ({kind}): {shown}")
            elif kind == "stdio":
                servers[name] = list_tools(target, env=extra, timeout=args.timeout)
            else:
                # Each remote server only gets the headers from its own config entry.
                servers[name] = list_tools_http(target, extra, timeout=args.timeout)
        except (LoadError, McpClientError) as exc:
            notes.append(f"Failed {name}: {exc}")
            failed += 1
    if not args.launch:
        notes.append("Nothing was scanned: pass --launch to start stdio servers and connect to remote servers.")
    return servers, notes, failed


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.launch and not args.config:
            raise UsageError("--launch only applies to --config")
        if args.header and not args.url:
            raise UsageError("--header only applies to --url (config entries use their own 'headers')")
        servers, notes, failed = collect(args)
    except (UsageError, LoadError, McpClientError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.command == "pin":
        for note in notes:
            print(note)
        if not servers:
            print("error: no servers were scanned, so nothing was pinned", file=sys.stderr)
            return 2
        Path(args.out).write_text(json.dumps(build_lock(servers), indent=2, sort_keys=True) + "\n",
                                  encoding="utf-8")
        print(f"Pinned {sum(map(len, servers.values()))} tool(s) from {len(servers)} server(s) to {args.out}")
        return 2 if failed else 0

    if not servers:
        print(render_text([], {}, notes) if args.format == "text" else render_json([], {}, notes))
        return 2 if args.launch else 0

    findings = scan_servers(servers, max_description=args.max_description)
    if args.lock:
        try:
            lock = json.loads(Path(args.lock).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: could not read lockfile {args.lock}: {exc}", file=sys.stderr)
            return 2
        findings += diff_lock(lock, servers)

    scanned = {server: len(tools) for server, tools in servers.items()}
    if failed:
        notes.append(f"Incomplete: {failed} server(s) could not be scanned (exit code 2).")
    render = render_json if args.format == "json" else render_text
    print(render(findings, scanned, notes))
    return 2 if failed else exit_code(findings, args.fail_on)
