"""Offline CLI; does not import ADK and does not need an API key."""
import argparse
import json
import sys
from pathlib import Path
from .engine import analyze_logs, read_log_file


def main() -> int:
    parser = argparse.ArgumentParser(description="TraceTriage: offline log incident triage")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=Path, help="Local UTF-8 log file")
    group.add_argument("--text", help="Paste a short log excerpt")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()
    try:
        contents = read_log_file(args.file) if args.file is not None else args.text
        result = analyze_logs(contents)
    except (ValueError, OSError, UnicodeError) as exc:
        print(f"TraceTriage error: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(result, indent=2))
        return 0
    print("=== TraceTriage | Evidence-first incident report ===")
    print(f"Log lines: {result['processed_lines']} | Severity: {result['severity']}")
    print(f"Hypothesis: {result['probable_root_cause'] or 'No recognized failure pattern'}")
    print(f"Verification: {result['root_cause_status']}")
    if result["top_signals"]:
        print("\nEvidence:")
        for s in result["top_signals"][:3]:
            print(f"  - {s['title']} ({s['count']} matching lines)")
            for e in s["evidence"][:2]:
                print(f"      L{e['line']}: {e['excerpt']}")
    print("\nSuggested checks:")
    for check in result["suggested_checks"]:
        print(f"  - {check}")
    print("\nNote: Hypotheses are not confirmed; sensitive data redaction is best-effort.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
