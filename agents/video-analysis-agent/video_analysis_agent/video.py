"""Video handling with FFmpeg: validation, audio extraction, optional cleanup."""

from __future__ import annotations

import importlib.util
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path

from .errors import VideoError

log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".mpg", ".mpeg", ".wmv", ".flv",
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac",  # audio-only works too
}
DENOISE_FILTER = "highpass=f=80,afftdn=nf=-25,loudnorm"
INSTALL_HINT = (
    "Install FFmpeg and make sure 'ffmpeg' and 'ffprobe' are on your PATH: "
    "Windows `winget install Gyan.FFmpeg`, macOS `brew install ffmpeg`, "
    "Linux `sudo apt install ffmpeg`."
)


def check_ffmpeg() -> None:
    missing = [t for t in ("ffmpeg", "ffprobe") if shutil.which(t) is None]
    if missing:
        raise VideoError(f"{' and '.join(missing)} not found. {INSTALL_HINT}")


def validate_input(path: Path) -> None:
    if not path.exists():
        raise VideoError(f"File not found: {path}")
    if not path.is_file():
        raise VideoError(f"Not a file: {path}")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise VideoError(
            f"Unsupported format '{path.suffix}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    if path.stat().st_size == 0:
        raise VideoError(f"File is empty: {path}")


def _run(cmd: list[str], what: str) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as exc:
        raise VideoError(f"Could not run {cmd[0]}: {exc}") from exc
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-5:])
        raise VideoError(f"{what} failed (file may be corrupt or unreadable):\n{tail}")
    return proc


def probe(path: Path) -> float:
    """Return duration in seconds; raise if the file has no audio track."""
    proc = _run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
         "-of", "json", str(path)],
        "Reading media info",
    )
    info = json.loads(proc.stdout or "{}")
    if not any(s.get("codec_type") == "audio" for s in info.get("streams", [])):
        raise VideoError("The file has no audio track, so there is nothing to transcribe.")
    try:
        return float(info["format"]["duration"])
    except (KeyError, ValueError):
        return 0.0


def extract_audio(src: Path, dest: Path, denoise: bool = False) -> Path:
    """Extract 16 kHz mono WAV (what Whisper expects). Optionally denoise/normalize."""
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000"]
    if denoise:
        cmd += ["-af", DENOISE_FILTER]
    cmd += ["-c:a", "pcm_s16le", str(dest)]
    _run(cmd, "Audio extraction")
    if not dest.exists() or dest.stat().st_size == 0:
        raise VideoError("Audio extraction produced an empty file.")
    return dest


def separate_vocals(wav: Path, workdir: Path) -> Path:
    """Optional: isolate speech from music with Demucs (`pip install demucs`)."""
    if importlib.util.find_spec("demucs") is None:
        raise VideoError("--separate-vocals needs Demucs. Install it with: pip install demucs")
    log.info("Separating vocals with Demucs (slow on CPU)...")
    _run([sys.executable, "-m", "demucs", "--two-stems=vocals", "-o", str(workdir), str(wav)], "Vocal separation")
    found = list(workdir.glob(f"*/{wav.stem}/vocals.wav"))
    if not found:
        raise VideoError("Demucs finished but no vocals track was found.")
    out = workdir / "vocals_16k.wav"
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(found[0]), "-ac", "1", "-ar", "16000", str(out)], "Resampling vocals")
    return out
