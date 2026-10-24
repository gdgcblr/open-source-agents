"""Local speech-to-text with faster-whisper (open-source Whisper, no API key)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

from .errors import TranscriptionError
from .schemas import Transcript, TranscriptSegment

log = logging.getLogger(__name__)

LOW_LOGPROB = -1.0
HIGH_NO_SPEECH = 0.6


def _is_gpu_error(exc: Exception) -> bool:
    return any(w in str(exc).lower() for w in ("cublas", "cudnn", "cuda"))


def _run_whisper(model_cls, audio, model_size, device, compute, language, duration):
    model = model_cls(model_size, device=device, compute_type=compute)
    # Segments stream lazily, so long recordings are processed incrementally.
    stream, info = model.transcribe(str(audio), language=language, vad_filter=True, beam_size=5)
    total = duration or info.duration or 0.0
    segments: list[TranscriptSegment] = []
    for seg in stream:
        text = seg.text.strip()
        if not text:
            continue
        low = seg.avg_logprob < LOW_LOGPROB or seg.no_speech_prob > HIGH_NO_SPEECH
        segments.append(TranscriptSegment(start=seg.start, end=seg.end, text=text, low_confidence=low))
        if total and sys.stderr.isatty():
            print(f"\rTranscribing... {min(100, int(seg.end / total * 100))}%", end="", file=sys.stderr)
    if total and sys.stderr.isatty():
        print(file=sys.stderr)
    return segments, info, total


def transcribe(
    audio: Path,
    model_size: Optional[str] = None,
    language: Optional[str] = None,
    duration: float = 0.0,
) -> Transcript:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise TranscriptionError("faster-whisper is not installed. Run: pip install -r requirements.txt") from None

    model_size = model_size or os.environ.get("WHISPER_MODEL", "base")
    device = os.environ.get("WHISPER_DEVICE", "cpu")
    compute = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
    log.info("Loading Whisper model '%s' (first use downloads it)...", model_size)
    try:
        try:
            segments, info, total = _run_whisper(WhisperModel, audio, model_size, device, compute, language, duration)
        except Exception as exc:
            if device != "auto" or not _is_gpu_error(exc):
                raise
            log.warning("GPU unavailable (%s); falling back to CPU.", exc)
            segments, info, total = _run_whisper(WhisperModel, audio, model_size, "cpu", compute, language, duration)
    except Exception as exc:  # model download/decoding errors are varied
        raise TranscriptionError(f"Transcription failed: {type(exc).__name__}: {exc}") from exc

    if not segments:
        raise TranscriptionError(
            "No speech was detected. The audio may be silent, music-only, or too noisy "
            "(try --denoise or --separate-vocals)."
        )
    return Transcript(language=info.language, duration=total, segments=segments)
