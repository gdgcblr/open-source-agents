"""Command-line entry point for PR Draft Agent."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

from .agent import GenerationError, generate_draft
from .config import ConfigError, load_settings
from .output import OutputError, validate_and_render
from .repository import InputError, RepositorySnapshot, capture_snapshot, validate_intent

EXIT_OK = 0
EXIT_LOCAL = 2
EXIT_GENERATION = 3
EXIT_OUTPUT = 4
EXIT_INTERRUPTED = 130

OUTPUT_ERROR_CODES = {"TOOLS_NOT_USED", "NO_FINAL_RESPONSE", "INVALID_DRAFT", "OUTPUT_TOO_LARGE"}

TRANSFER_NOTICE = (
    "Sending the staged diff, PR template (or fallback), and optional author intent to Gemini. "
    "API usage may be billable. Use --check to inspect locally without a model call."
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pr-draft-agent",
        description="Draft an editable Markdown PR title and description from staged Git changes.",
        epilog=(
            "The model receives the staged diff, the selected PR template, and optional intent. "
            "Nothing is staged, committed, or published by this tool."
        ),
    )
    parser.add_argument(
        "--repo",
        required=True,
        type=Path,
        metavar="PATH",
        help="path inside the Git working tree to inspect (required; never implicit)",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check",
        action="store_true",
        help="validate inputs and print a local metadata report; no model call",
    )
    mode.add_argument(
        "--send-to-model",
        action="store_true",
        help="send validated source material to Gemini and print the draft",
    )
    parser.add_argument(
        "--intent",
        metavar="TEXT",
        help="optional author-provided motivation or context (max 2,048 UTF-8 bytes)",
    )
    return parser


def _configure_diagnostics() -> None:
    # SDK DEBUG logs can include full prompts, responses and request details.
    # Silence existing children as well as parents: children may have their own
    # DEBUG level and handlers, including those installed by SDK environment flags.
    provider_names = ("google", "google_adk", "google_genai", "httpx", "httpcore")
    names = set(provider_names)
    names.update(
        name
        for name in logging.Logger.manager.loggerDict
        if any(name.startswith(prefix + ".") for prefix in provider_names)
    )
    for name in names:
        provider_logger = logging.getLogger(name)
        provider_logger.handlers[:] = [logging.NullHandler()]
        provider_logger.propagate = False
        provider_logger.setLevel(logging.CRITICAL + 1)

    logger = logging.getLogger("pr_draft_agent")
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.handlers[:] = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)


def _print_check(snapshot: RepositorySnapshot, intent: str) -> None:
    print("Eligible: yes")
    print(f"Files: {len(snapshot.files)}")
    for changed in snapshot.files:
        print(f"  {changed.status} {changed.path}")
    print(f"Diff bytes: {len(snapshot.diff.encode('utf-8'))}")
    print(f"Template: {snapshot.template_source or '(fallback)'}")
    print(f"Template bytes: {len(snapshot.template.encode('utf-8'))}")
    print(f"Intent bytes: {len(intent.encode('utf-8'))}")
    print(f"Diff SHA-256: {snapshot.diff_sha256}")


def _fail(code: str, message: str, exit_code: int) -> int:
    print(f"Error: {message} ({code})", file=sys.stderr)
    return exit_code


def _generation_exit(code: str) -> int:
    return EXIT_OUTPUT if code in OUTPUT_ERROR_CODES else EXIT_GENERATION


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    intent = args.intent if args.intent is not None else ""
    stage = "local"

    try:
        snapshot = capture_snapshot(args.repo)
        intent = validate_intent(intent)

        if args.check:
            _print_check(snapshot, intent)
            return EXIT_OK

        # Credentials and model selection are checked only after the local
        # evidence has passed every boundary; --check never needs either.
        settings = load_settings(require_model=True)
        _configure_diagnostics()
        print(TRANSFER_NOTICE, file=sys.stderr)

        stage = "generation"
        started = time.monotonic()
        text = asyncio.run(generate_draft(snapshot, intent, settings.model))
        elapsed = time.monotonic() - started

        stage = "output"
        rendered = validate_and_render(text, snapshot)
        sys.stdout.write(rendered + "\n")
        sys.stdout.flush()
        print(f"Generated a draft in {elapsed:.1f}s. Review it before submitting.", file=sys.stderr)
        return EXIT_OK

    except InputError as exc:
        return _fail(exc.code, exc.message, EXIT_LOCAL)
    except ConfigError as exc:
        return _fail(exc.code, exc.message, EXIT_LOCAL)
    except GenerationError as exc:
        return _fail(exc.code, exc.message, _generation_exit(exc.code))
    except OutputError as exc:
        return _fail(exc.code, exc.message, EXIT_OUTPUT)
    except KeyboardInterrupt:
        return _fail("INTERRUPTED", "Interrupted before a draft was produced.", EXIT_INTERRUPTED)
    except Exception:  # noqa: BLE001 - unexpected failures must not leak tracebacks
        # Unexpected failures are reported without a traceback, which could
        # contain prompts, paths, or provider details.
        if stage == "output":
            return _fail("INVALID_DRAFT", "The generated draft could not be validated.", EXIT_OUTPUT)
        if stage == "generation":
            return _fail("AGENT_FAILED", "The agent failed unexpectedly; no draft was produced.", 3)
        return _fail(
            "UNEXPECTED_ERROR", "An unexpected local failure occurred; no draft was produced.", 2
        )


if __name__ == "__main__":
    raise SystemExit(main())
