"""Command-line interface: a scripted demo and a JSONL trace analyzer.

Trace format for `analyze` (one JSON object per line, blank lines ignored):
  tool     string, required   tool name
  args     object, optional   tool arguments (default {})
  session  string, optional   session id; each gets its own breaker (default "default")
  ok       bool,   optional   whether the call succeeded; feeds the error counter
"""

import argparse
import json
import sys

from breaker import CircuitBreaker
from dlp import check_args, redact, redact_obj

FIELDS_HELP = "Trace format" + __doc__.split("Trace format")[1].rstrip()


def _safe(text):
    return redact(str(text))[0]


# Scripted "agent" stuck retrying a failing fetch, after first poking at a .env file.
DEMO_SCRIPT = [("read_file", {"path": "config/.env"}, True)] + [
    step for _ in range(8)
    for step in (("search", {"q": "latest release notes"}, True),
                 ("fetch", {"url": "https://example.invalid/notes"}, False))
]


def run_protected(script, execute, out=sys.stdout):
    """Run script through guardrails + breaker; execute(tool, args, ok) is only called for allowed steps."""
    breaker, executed = CircuitBreaker(), 0
    for i, (tool, args, ok) in enumerate(script, 1):
        hits = check_args(args)
        if hits:
            print(f"  #{i:<2} {tool:<9} BLOCKED [guardrail] {', '.join(hits)}", file=out)
            continue
        d = breaker.check(tool, args)
        if not d.allowed:
            print(f"  #{i:<2} {tool:<9} BLOCKED [{d.code}] {d.reason}", file=out)
            print("  -> breaker tripped, agent halted", file=out)
            break
        ok = execute(tool, args, ok)
        executed += 1
        breaker.record_result(ok)
        print(f"  #{i:<2} {tool:<9} {'ok' if ok else 'ERROR'}", file=out)
    return executed


def demo(out=sys.stdout):
    simulate = lambda tool, args, ok: ok  # stand-in for a real tool; no side effects
    print("== Unprotected run ==", file=out)
    for i, (tool, args, ok) in enumerate(DEMO_SCRIPT, 1):
        print(f"  #{i:<2} {tool:<9} {'ok' if simulate(tool, args, ok) else 'ERROR'}", file=out)
    print(f"  -> {len(DEMO_SCRIPT)} calls executed, "
          f"{sum(not ok for *_, ok in DEMO_SCRIPT)} failed, nothing stopped the loop\n", file=out)

    print("== Protected run (CircuitBreaker + guardrails) ==", file=out)
    executed = run_protected(DEMO_SCRIPT, simulate, out)
    print(f"  -> {executed} calls executed instead of {len(DEMO_SCRIPT)}", file=out)
    return 0


def _parse(line):
    """Return (record, error). Error messages never include line content."""
    try:
        rec = json.loads(line.rstrip("\r\n"))
    except json.JSONDecodeError as e:
        return None, f"invalid JSON ({e.msg} at column {e.colno})"
    if not isinstance(rec, dict):
        return None, "expected a JSON object"
    if not isinstance(rec.get("tool"), str) or not rec["tool"]:
        return None, "missing or empty 'tool' string"
    if not isinstance(rec.get("args", {}), dict):
        return None, "'args' must be an object"
    if "ok" in rec and not isinstance(rec["ok"], bool):
        return None, "'ok' must be true or false"
    if not isinstance(rec.get("session", ""), str):
        return None, "'session' must be a string"
    return rec, None


def analyze(path, out=sys.stdout):
    """Exit codes: 0 clean, 1 issues found, 2 file unreadable."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError) as e:
        print(f"error: cannot read {path}: {type(e).__name__}", file=out)
        return 2

    breakers, stats = {}, {"calls": 0, "blocked": 0, "flagged": 0, "malformed": 0, "secrets": 0}
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        rec, err = _parse(line)
        if err:
            stats["malformed"] += 1
            print(f"line {n}: MALFORMED {err}", file=out)
            continue
        stats["calls"] += 1
        session, tool, args = rec.get("session", "default"), rec["tool"], rec.get("args", {})
        shown_args, secrets = redact_obj(args)
        stats["secrets"] += len(secrets)
        breaker = breakers.setdefault(session, CircuitBreaker())
        d = breaker.check(tool, args)
        hits = check_args(args)
        notes = []
        if not d.allowed:
            stats["blocked"] += 1
            notes.append(f"WOULD BLOCK [{d.code}] {_safe(d.reason)}")
        if hits:
            stats["flagged"] += 1
            notes.append(f"GUARDRAIL {', '.join(hits)}")
        if secrets:
            notes.append(f"SECRETS {', '.join(sorted(set(secrets)))}")
        if d.allowed and "ok" in rec:
            breaker.record_result(rec["ok"])
        status = " | ".join(notes) or "allowed"
        if "ok" in rec:
            status += " (call succeeded)" if rec["ok"] else " (call FAILED)"
        print(f"line {n}: [{_safe(session)}] {_safe(tool)} "
              f"{json.dumps(shown_args, sort_keys=True, default=str)} -> {status}", file=out)

    print(f"\nSummary: {stats['calls']} calls in {len(breakers)} session(s), "
          f"{stats['blocked']} would be blocked, {stats['flagged']} guardrail hits, "
          f"{stats['secrets']} secrets redacted, {stats['malformed']} malformed lines", file=out)
    return 1 if stats["blocked"] or stats["flagged"] or stats["secrets"] or stats["malformed"] else 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="cli.py", description="Circuit breaker for agent tool calls.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="simulate a looping agent with and without the breaker")
    p = sub.add_parser("analyze", help="replay a JSONL tool-call trace",
                       description=FIELDS_HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("jsonl_file")
    a = parser.parse_args(argv)
    return demo() if a.command == "demo" else analyze(a.jsonl_file)


if __name__ == "__main__":
    sys.exit(main())
