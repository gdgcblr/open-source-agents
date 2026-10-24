"""Command line entry point: python -m firstrun <folder or GitHub URL>."""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

from .agent import Settings, run_check

STAGES = ("understand", "attempt", "investigate", "repair", "verify", "report")
EXIT_CODES = {"passed": 0, "fixed": 1, "failed": 1, "blocked": 2, "error": 3}


def parse_env_file(path: Path) -> dict[str, str]:
    return parse_env_text(path.read_text(encoding="utf-8"))


def parse_env_text(text: str) -> dict[str, str]:
    """KEY=VALUE lines, comments and `export` allowed, surrounding quotes stripped."""
    env = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        env[key.strip()] = value
    return env


PLACEHOLDER_RE = re.compile(r"^(|your[_-].*|.*_here|<.*>|changeme|xxx+|\.\.\.)$", re.IGNORECASE)


def load_own_dotenv() -> None:
    """Pick up GEMINI_API_KEY / FIRSTRUN_MODEL from a .env next to FirstRun, without overriding.

    Values still set to the .env.example placeholder are ignored, so a fresh copy of the example
    file means "offline" rather than a doomed API call with a fake key.
    """
    path = Path(__file__).resolve().parents[1] / ".env"
    if path.is_file():
        for key, value in parse_env_file(path).items():
            if not PLACEHOLDER_RE.match(value.strip()):
                os.environ.setdefault(key, value)


class Printer:
    def __init__(self, verbose: bool, quiet: bool):
        self.verbose, self.quiet = verbose, quiet
        self.color = sys.stdout.isatty() and "NO_COLOR" not in os.environ
        self.step_started = 0.0

    def c(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.color else text

    def __call__(self, kind: str, message: str, data: Optional[dict] = None) -> None:
        data = data or {}
        if self.quiet and kind not in ("warn",):
            return
        if kind == "stage" and data.get("state") == "start":
            n = STAGES.index(data["stage"]) + 1 if data.get("stage") in STAGES else 0
            print(self.c(f"\n[{n}/6] {data['stage'].capitalize()}", "1"))
        elif kind == "stage" and data.get("state") == "fail" and data.get("stage") == "attempt":
            print(self.c("      failed as documented, keeping that result before trying a fix", "33"))
        elif kind == "step_start":
            self.step_started = time.time()
            cmd = " ".join(str(data.get("command", "")).split())
            print(f"      $ {cmd[:100]}", flush=True)
        elif kind == "step_end":
            status = data.get("status", "")
            took = time.time() - self.step_started
            colour = "32" if status in ("passed", "alive") else "31" if status in ("failed", "timeout") else "2"
            code = data.get("exit_code")
            extra = f" (exit {code})" if code not in (None, 0) else ""
            print(self.c(f"        {status}{extra}, {took:.1f}s", colour))
        elif kind == "log" and self.verbose:
            print(self.c(f"        | {message}", "2"))
        elif kind == "plan":
            plan = data.get("plan") or {}
            print(f"      {message}")
            for s in plan.get("skipped", []):
                cmd = " ".join(str(s.get("command", "")).split())[:60]
                print(self.c(f"      skip  {cmd}  ({s.get('reason')})", "2"))
        elif kind == "diagnosis":
            d = (data.get("diagnosis") or {})
            print(self.c(f"      found: {message}", "1"))
            for ev in d.get("evidence", [])[:4]:
                loc = f"{ev.get('file')}:{ev.get('line')}" if ev.get("line") else ev.get("file")
                print(self.c(f"        {loc}  {ev.get('note')}", "2"))
        elif kind == "diff":
            print(f"      {message}")
        elif kind == "tool_call":
            print(self.c(f"      agent: {message}", "36"))
        elif kind == "warn":
            print(self.c(f"      warning: {message}", "33"), file=sys.stderr)
        elif kind == "info":
            print(f"      {message}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m firstrun",
        description="Check whether a newcomer can run a project by following its README.",
    )
    p.add_argument("target", help="project folder or GitHub URL (tree URLs with a branch and path work too)")
    p.add_argument("--subdir", help="project folder inside the target, e.g. agents/my-agent")
    p.add_argument("--sandbox", choices=("docker", "local"), default="docker",
                   help="docker (default, isolated) or local (temp folder + fresh venv on this machine)")
    p.add_argument("--image", default="python:3.12-slim", help="Docker image for the fresh environment")
    p.add_argument("--offline", action="store_true", help="skip Gemini and use the built-in rules only")
    p.add_argument("--env-file", type=Path, help="KEY=VALUE file with secrets the project needs")
    p.add_argument("--pass-env", action="append", default=[], metavar="NAME",
                   help="pass this variable from your shell into the sandbox (repeatable)")
    p.add_argument("--max-rounds", type=int, default=2, help="repair attempts before giving up (default 2)")
    p.add_argument("--no-repair", action="store_true", help="only report the documented run, do not try fixes")
    p.add_argument("--timeout", type=int, default=900, help="seconds allowed for each sandbox run")
    p.add_argument("--watch", type=int, default=20,
                   help="seconds a server or UI must stay up to count as started (default 20)")
    p.add_argument("--out", type=Path, default=Path("runs"), help="where run folders are written")
    p.add_argument("--comment-file", type=Path, metavar="PATH",
                   help="also write a short PR comment version of the report to PATH")
    p.add_argument("--ci", action="store_true",
                   help="exit 0 only if the project works as documented (1 failed or fixed, 2 blocked, 3 error)")
    p.add_argument("-v", "--verbose", action="store_true", help="stream sandbox output")
    p.add_argument("-q", "--quiet", action="store_true", help="print only the verdict")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    load_own_dotenv()

    env: dict[str, str] = {}
    if args.env_file:
        if not args.env_file.is_file():
            print(f"env file not found: {args.env_file}", file=sys.stderr)
            return 3
        env.update(parse_env_file(args.env_file))
    for name in args.pass_env:
        if name in os.environ:
            env[name] = os.environ[name]
        else:
            print(f"warning: --pass-env {name} is not set in this shell", file=sys.stderr)

    settings = Settings(
        sandbox=args.sandbox, image=args.image, offline=args.offline,
        max_rounds=args.max_rounds, repair=not args.no_repair, timeout=args.timeout,
        watch_seconds=args.watch, env=env, out_dir=args.out,
    )
    printer = Printer(verbose=args.verbose, quiet=args.quiet)
    if not args.quiet:
        print(f"FirstRun: checking {args.target}" + (f" ({args.subdir})" if args.subdir else ""))
    report, run_dir = run_check(args.target, settings, subdir=args.subdir, on_event=printer)

    colour = {"passed": "32", "fixed": "32", "blocked": "33"}.get(report.verdict, "31")
    print()
    print(printer.c(f"Verdict: {report.verdict.upper()}", "1;" + colour))
    print(report.headline)
    if report.final_diff and not args.quiet:
        print()
        print(report.final_diff.rstrip())
    print(f"\nReport: {run_dir / 'report.md'}")
    if args.comment_file:
        from .comment import render_comment

        args.comment_file.write_text(render_comment(report), encoding="utf-8")
        print(f"PR comment: {args.comment_file}")
    if report.verdict == "error":
        return 3
    return EXIT_CODES.get(report.verdict, 1) if args.ci else 0
