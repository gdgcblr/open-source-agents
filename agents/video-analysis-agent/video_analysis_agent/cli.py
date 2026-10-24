"""Command-line interface."""

from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import shutil
import sys
from pathlib import Path

from . import __version__
from .errors import AgentError, ConfigError
from .llm import KEY_ENV, PROVIDERS, build_client
from .pipeline import Options, run
from .report import render_markdown


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="video_analysis_agent",
        description="Turn a video into a structured, evidence-backed report (summary, decisions, action items...).",
    )
    p.add_argument("input", nargs="?", help="video/audio file (mp4, mov, ...) or a transcript.json from a previous run")
    p.add_argument("-o", "--out-dir", help="output folder (default: output/<input-name>)")
    p.add_argument("--format", choices=["md", "json", "both"], default="both", help="report formats to write (default: both)")
    p.add_argument("--provider", choices=PROVIDERS, help="LLM provider (default: auto-detect from your API key)")
    p.add_argument("--llm-model", help="LLM model name (default depends on provider)")
    p.add_argument("--whisper-model", help="Whisper size: tiny|base|small|medium|large-v3 (default: base)")
    p.add_argument("--language", help="spoken language code, e.g. en, hi (default: auto-detect)")
    p.add_argument("--denoise", action="store_true", help="optional: denoise + normalize audio with FFmpeg before transcribing")
    p.add_argument("--separate-vocals", action="store_true", help="optional: strip background music with Demucs (pip install demucs; slow)")
    p.add_argument("--chunk-chars", type=int, default=12000, help="max transcript characters per LLM call (default: 12000)")
    p.add_argument("--no-print", action="store_true", help="do not print the report to the terminal")
    p.add_argument("--check", action="store_true", help="check FFmpeg, Whisper and API key setup, then exit")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _check() -> int:
    ok = True

    def line(label: str, good: bool, detail: str) -> None:
        nonlocal ok
        ok &= good
        print(f"[{'ok' if good else '!!'}] {label}: {detail}")

    line("ffmpeg", bool(shutil.which("ffmpeg")), shutil.which("ffmpeg") or "not found on PATH")
    line("ffprobe", bool(shutil.which("ffprobe")), shutil.which("ffprobe") or "not found on PATH")
    line("faster-whisper", importlib.util.find_spec("faster_whisper") is not None, "installed" if importlib.util.find_spec("faster_whisper") else "pip install -r requirements.txt")
    found = [p for p in PROVIDERS if any(os.environ.get(v) for v in KEY_ENV[p])]
    line("LLM API key", bool(found), f"found for: {', '.join(found)}" if found else "none set (see README); you will be prompted at run time")
    print(f"[--] demucs (optional, for --separate-vocals): {'installed' if importlib.util.find_spec('demucs') else 'not installed'}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s: %(message)s", stream=sys.stderr)
    _load_dotenv()

    if args.check:
        return _check()
    if not args.input:
        _parser().print_usage(sys.stderr)
        print("error: an input file is required (or use --check).", file=sys.stderr)
        return 1
    if args.chunk_chars < 1000:
        print("error: --chunk-chars must be at least 1000.", file=sys.stderr)
        return 1

    src = Path(args.input).expanduser()
    out_dir = Path(args.out_dir) if args.out_dir else Path("output") / src.stem
    opts = Options(
        out_dir=out_dir,
        formats=args.format,
        whisper_model=args.whisper_model,
        language=args.language,
        denoise=args.denoise,
        separate_vocals=args.separate_vocals,
        chunk_chars=args.chunk_chars,
    )
    try:
        if not src.exists():
            raise ConfigError(f"File not found: {src}")
        llm = build_client(args.provider, args.llm_model)  # fail on bad config before slow transcription
        report, written = run(src, llm, opts)
    except AgentError as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        return 2 if not isinstance(exc, ConfigError) else 1
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130

    if not args.no_print:
        print(render_markdown(report))
    print("Files written:", *[f"  {p}" for p in written], sep="\n", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
