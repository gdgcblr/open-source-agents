"""CLI: talk notes (+ optional slide) -> script.md + deck.json for smart-glasses cues.

Example:
    python main.py --notes examples/notes.txt --minutes 2 --language en
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from glasses_speaker_cue_agent import guardrails
from glasses_speaker_cue_agent.config import MAX_IMAGE_BYTES, ConfigError
from glasses_speaker_cue_agent.deck import Deck, DraftError, to_script_markdown
from glasses_speaker_cue_agent.duration import format_seconds
from glasses_speaker_cue_agent.pipeline import (
    CueRequest,
    UpstreamError,
    create_deck,
    quiet_sdk_logs,
)

EXIT_BAD_INPUT = 2
EXIT_BLOCKED = 3
EXIT_UPSTREAM = 4


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--notes", required=True, help="Path to a text file with your notes.")
    parser.add_argument("--minutes", type=float, default=2.0, help="Time slot (default: 2).")
    parser.add_argument("--slide", help="Optional slide image (PNG, JPEG or WebP).")
    parser.add_argument("--language", default="en", help="Output language code (default: en).")
    parser.add_argument("--no-qa", action="store_true", help="Skip the Q&A section.")
    parser.add_argument(
        "--keep-pii", action="store_true", help="Send emails/phone numbers without redacting."
    )
    parser.add_argument("--out", default="out", help="Output folder (default: out).")
    parser.add_argument("--verbose", action="store_true", help="Show ADK/Gemini internal logs.")
    return parser.parse_args(argv)


def write_outputs(deck: Deck, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "deck.json").write_text(
        json.dumps(deck.model_dump(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out_dir / "script.md").write_text(to_script_markdown(deck), encoding="utf-8")


def _read_notes(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise guardrails.InputError(f"Notes file {path} is not UTF-8 text.") from None
    except OSError as exc:
        raise guardrails.InputError(f"Cannot read notes file {path}: {exc.strerror}.") from None


def _read_slide(path: str) -> bytes:
    """Checks the size before reading so a huge file is never loaded into memory."""
    try:
        if Path(path).stat().st_size > MAX_IMAGE_BYTES:
            raise guardrails.InputError(
                f"Slide image is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB."
            )
        return Path(path).read_bytes()
    except OSError as exc:
        raise guardrails.InputError(f"Cannot read slide {path}: {exc.strerror}.") from None


def run(args: argparse.Namespace) -> int:
    request = CueRequest(
        notes=_read_notes(args.notes),
        minutes=args.minutes,
        language=args.language,
        include_qa=not args.no_qa,
        image=_read_slide(args.slide) if args.slide else None,
        keep_pii=args.keep_pii,
    )
    deck = asyncio.run(create_deck(request, progress=_log))
    write_outputs(deck, Path(args.out))

    status = "fits" if deck.fitsTarget else "outside target"
    print(
        f"\n{deck.title}\n"
        f"{format_seconds(deck.estimatedDurationSeconds)} "
        f"(target {format_seconds(deck.targetSeconds)}, {status})"
        f" · {len(deck.cues)} cues · {len(deck.qa)} Q&A\n"
        f"Wrote {Path(args.out) / 'script.md'} and {Path(args.out) / 'deck.json'}"
    )
    for warning in deck.warnings:
        print(f"Warning: {warning}")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path(__file__).with_name(".env"))
    args = parse_args(argv)
    if not args.verbose:
        quiet_sdk_logs()
    try:
        return run(args)
    except (guardrails.InputError, ConfigError) as exc:
        _log(f"Error: {exc}")
        return EXIT_BAD_INPUT
    except guardrails.BlockedError as exc:
        _log(f"Blocked: {exc}")
        return EXIT_BLOCKED
    except DraftError as exc:
        _log(f"Error: the model's reply could not be used. {exc}")
        return EXIT_UPSTREAM
    except UpstreamError as exc:
        _log(f"Error: {exc}")
        return EXIT_UPSTREAM


if __name__ == "__main__":
    sys.exit(main())
