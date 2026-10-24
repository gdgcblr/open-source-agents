"""Local filesystem storage for call audio."""

import asyncio
from pathlib import Path
from typing import BinaryIO

ALLOWED_AUDIO_SUFFIXES = frozenset(
    {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".webm", ".mp4"}
)
_COPY_CHUNK_BYTES = 1024 * 1024


class UploadTooLargeError(Exception):
    """Raised when an uploaded file exceeds the configured size limit."""


class RecordingStorage:
    """Stores audio files in one directory. Filenames are generated from call IDs, never taken
    from user input, so a caller cannot write or read outside the storage root."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def ensure_root(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)

    def path_for(self, filename: str) -> Path:
        return self._root / filename

    async def save_bytes(self, call_id: str, suffix: str, data: bytes) -> str:
        filename = f"{call_id}{suffix}"
        await asyncio.to_thread(self.path_for(filename).write_bytes, data)
        return filename

    async def save_stream(self, call_id: str, suffix: str, source: BinaryIO, max_bytes: int) -> str:
        filename = f"{call_id}{suffix}"
        await asyncio.to_thread(_copy_with_limit, source, self.path_for(filename), max_bytes)
        return filename

    async def read(self, filename: str) -> bytes:
        return await asyncio.to_thread(self.path_for(filename).read_bytes)

    def delete(self, filename: str) -> None:
        self.path_for(filename).unlink(missing_ok=True)


def _copy_with_limit(source: BinaryIO, destination: Path, max_bytes: int) -> None:
    written = 0
    try:
        with destination.open("wb") as out:
            while chunk := source.read(_COPY_CHUNK_BYTES):
                written += len(chunk)
                if written > max_bytes:
                    raise UploadTooLargeError(
                        f"File exceeds the {max_bytes // (1024 * 1024)} MB limit"
                    )
                out.write(chunk)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
