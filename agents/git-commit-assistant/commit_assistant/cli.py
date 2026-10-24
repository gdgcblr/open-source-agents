"""Command-line interface and orchestration.

Parses arguments, acquires the diff (from ``git diff --staged`` or a
``--diff-file``), resolves a provider, prints the generated commit
message to stdout, and maps failures to friendly messages / exit codes.

Exit codes:
    0  success
    1  no staged changes / empty diff
    2  git missing, unreadable diff file, or a provider/config error
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from typing import List, Optional

from .providers import ProviderError, get_provider, resolve_provider

EXIT_OK = 0
EXIT_NO_CHANGES = 1
EXIT_ERROR = 2

_EPILOG = (
    "examples:\n"
    "  python main.py                              # use staged changes, auto provider\n"
    "  python main.py --provider mock              # force the offline heuristic\n"
    "  python main.py --diff-file changes.diff     # read a diff from a file\n"
    "  python main.py --no-body                    # header line only\n"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="git-commit-assistant",
        description=(
            "Generate a Conventional Commits message from the staged git diff. "
            "Defaults to an offline, deterministic heuristic so it runs with no API key."
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--provider",
        choices=["auto", "mock", "openai"],
        default="auto",
        help="LLM provider to use (default: auto -> openai if key set, else mock).",
    )
    parser.add_argument(
        "--diff-file",
        metavar="PATH",
        help="Read the diff from a file instead of running git.",
    )
    parser.add_argument(
        "--model",
        metavar="NAME",
        help="Model name override (openai only; ignored by the mock provider).",
    )
    parser.add_argument(
        "--no-body",
        action="store_true",
        help="Emit only the header line, no bullet-point body.",
    )
    return parser


def read_staged_diff() -> str:
    """Return the output of ``git diff --staged``.

    Raises :class:`ProviderError` if git is not installed or the command
    fails for a reason other than there simply being no staged changes.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--staged"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise ProviderError(
            "git was not found on PATH. Install git, or pass --diff-file to read a diff."
        ) from exc
    if result.returncode != 0:
        stderr = result.stderr.strip() or "unknown error"
        raise ProviderError(f"'git diff --staged' failed: {stderr}")
    return result.stdout


def read_diff_file(path: str) -> str:
    """Read diff text from ``path`` with a friendly error if it is missing."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except FileNotFoundError as exc:
        raise ProviderError(f"Diff file not found: {path}") from exc
    except OSError as exc:
        raise ProviderError(f"Could not read diff file '{path}': {exc}") from exc


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # The mock provider has no model concept; note it but do not fail.
    resolved = resolve_provider(
        None if args.provider == "auto" else args.provider,
        os.environ,
    )
    if args.model and resolved == "mock":
        print(
            "note: --model is ignored by the mock provider.",
            file=sys.stderr,
        )

    try:
        if args.diff_file:
            diff_text = read_diff_file(args.diff_file)
        else:
            diff_text = read_staged_diff()
    except ProviderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if not diff_text.strip():
        print(
            "No staged changes found. Stage files with 'git add' first, "
            "or pass --diff-file.",
            file=sys.stderr,
        )
        return EXIT_NO_CHANGES

    try:
        provider = get_provider(resolved)
        message = provider.generate(diff_text, model=args.model, no_body=args.no_body)
    except ProviderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    print(message)
    return EXIT_OK
