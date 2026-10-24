"""End-to-end workflow: input file -> transcript -> analysis -> report files."""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from . import video
from .analysis import DEFAULT_CHUNK_CHARS, analyze
from .errors import AgentError, VideoError
from .llm import LLMClient
from .report import write_outputs
from .schemas import Report, ReportMeta, Transcript
from .transcribe import transcribe

log = logging.getLogger(__name__)


@dataclass
class Options:
    out_dir: Path
    formats: str = "both"
    whisper_model: Optional[str] = None
    language: Optional[str] = None
    denoise: bool = False
    separate_vocals: bool = False
    chunk_chars: int = DEFAULT_CHUNK_CHARS


def load_transcript(path: Path) -> Transcript:
    try:
        return Transcript.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise VideoError(f"Not a valid transcript.json: {exc}") from exc


def get_transcript(src: Path, opts: Options) -> tuple[Transcript, list[str]]:
    """Return (transcript, preprocessing steps applied)."""
    if src.suffix.lower() == ".json":
        log.info("Loading existing transcript (skipping FFmpeg and Whisper).")
        return load_transcript(src), []

    video.validate_input(src)
    video.check_ffmpeg()
    duration = video.probe(src)
    steps: list[str] = []
    with tempfile.TemporaryDirectory(prefix="vaa-") as tmp:
        work = Path(tmp)
        log.info("Extracting audio with FFmpeg...")
        audio = video.extract_audio(src, work / "audio.wav", denoise=opts.denoise)
        if opts.denoise:
            steps.append("denoise+normalize")
        if opts.separate_vocals:
            audio = video.separate_vocals(audio, work)
            steps.append("vocal separation (demucs)")
        transcript = transcribe(audio, opts.whisper_model, opts.language, duration)
    transcript.source = src.name
    return transcript, steps


def run(src: Path, llm: LLMClient, opts: Options) -> tuple[Report, list[Path]]:
    transcript, steps = get_transcript(src, opts)
    transcript.source = transcript.source or src.name

    # Save the transcript first so an LLM failure never costs the (slow) transcription.
    opts.out_dir.mkdir(parents=True, exist_ok=True)
    (opts.out_dir / "transcript.json").write_text(transcript.model_dump_json(indent=2), encoding="utf-8")

    try:
        analysis, warnings = analyze(transcript, llm, opts.chunk_chars)
    except AgentError as exc:
        raise type(exc)(
            f"{exc}\nThe transcript was saved to {opts.out_dir / 'transcript.json'}; "
            f"re-run with that file as input to retry only the analysis."
        ) from exc

    report = Report(
        meta=ReportMeta(
            source=transcript.source or src.name,
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            duration=transcript.duration,
            language=transcript.language,
            llm_provider=llm.provider,
            llm_model=llm.model,
            whisper_model=None if src.suffix.lower() == ".json" else (opts.whisper_model or os.environ.get("WHISPER_MODEL", "base")),
            audio_preprocessing=steps,
        ),
        analysis=analysis,
        warnings=warnings,
        transcript=transcript,
    )
    return report, write_outputs(report, opts.out_dir, opts.formats)
