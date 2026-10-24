"""`python -m secret_scanner scan <path> [--staged] [--no-llm] [--json] [--model NAME]`"""

from __future__ import annotations

import argparse
import subprocess
import sys

from . import report
from .llm import OllamaError, OllamaUnavailable
from .scanner import scan


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="secret_scanner", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("scan", help="scan a file or directory")
    s.add_argument("path", nargs="?", default=".")
    s.add_argument("--staged", action="store_true", help="scan the git index (staged blobs) of the repo at PATH")
    s.add_argument("--no-llm", action="store_true", help="skip LLM triage (all matches reported as unverified)")
    s.add_argument("--json", action="store_true", help="machine-readable output (redacted)")
    s.add_argument("--model", help="Ollama model (default: $OLLAMA_MODEL or gemma4:e2b-it-q4_K_M)")
    s.add_argument("--require-llm", action="store_true",
                   help="exit 2 instead of falling back to --no-llm when Ollama/model is unavailable")
    s.add_argument("--max-llm-candidates", type=int, default=200,
                   help="cap on candidates sent to the LLM; the rest are reported as unverified (default 200)")
    s.add_argument("--host", help="Ollama host (default: $OLLAMA_HOST or http://localhost:11434)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    quiet = args.json or not sys.stderr.isatty()

    def progress(i: int, n: int) -> None:
        if not quiet:
            print(f"\rLLM triage {i}/{n}", end="", file=sys.stderr, flush=True)

    try:
        result = scan(args.path, use_llm=not args.no_llm, model=args.model, host=args.host,
                      staged=args.staged, progress=progress,
                      fallback_to_no_llm=not args.require_llm, max_llm_candidates=args.max_llm_candidates)
    except OllamaUnavailable as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except OllamaError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"error: {type(e).__name__}: {e if isinstance(e, FileNotFoundError) else 'git command failed (is this a git repo?)'}",
              file=sys.stderr)
        return 2
    if not quiet:
        print(file=sys.stderr)
    for w in result.warnings:
        print(f"warning: {w}", file=sys.stderr)
    print(report.to_json(result) if args.json else report.to_markdown(result))
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
