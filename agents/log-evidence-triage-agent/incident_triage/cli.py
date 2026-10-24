"""Offline CLI with optional validated AI selection; no SDK import by default."""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from .credibility import citations_valid
from .engine import read_log_file
from .investigation import investigate


def main() -> int:
    parser = argparse.ArgumentParser(description="TraceGuard AI: evidence-driven incident investigation")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=Path, help="Local UTF-8 .log, .txt, or .jsonl file")
    group.add_argument("--text", help="Paste a short log excerpt")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--product", choices=("php", "nodejs"), default="")
    parser.add_argument("--version", default="")
    parser.add_argument("--internet-facing", action="store_true")
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--ai", action="store_true", help="Optional Gemini/ADK selection with offline fallback")
    args = parser.parse_args()
    try:
        if args.ai:
            try:
                from dotenv import load_dotenv
                from .config import PROJECT_ROOT
                load_dotenv(PROJECT_ROOT / ".env")
            except ImportError:
                pass
        contents = read_log_file(args.file) if args.file is not None else args.text
        result = investigate(contents, args.product, args.version, args.internet_facing, args.production)
        if not citations_valid(result):
            raise ValueError("Internal evidence validation failed")
        if args.ai:
            from .ai import enhance
            result = asyncio.run(enhance(result))
    except (ValueError, OSError, UnicodeError) as exc:
        message = str(exc) if isinstance(exc, ValueError) else "Cannot read input; check file permissions and UTF-8 encoding."
        print(f"TraceGuard error: {message}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(result, indent=2))
        return 0
    print(f"=== TraceGuard AI | {result['mode']} ===")
    print(result["summary"])
    for finding in result["findings"]:
        print(f"- {finding['text']} [{', '.join(finding['evidence_refs'])}]")
    for unknown in result["unknowns"]:
        print(f"Unknown: {unknown}")
    if "fallback_reason" in result:
        print(result["fallback_reason"])
    print("Required human decision: " + result["escalation"]["required_human_decision"])
    for step in result["next_steps"] + result["analysis"]["suggested_checks"]:
        print(f"Next: {step}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
