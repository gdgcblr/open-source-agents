"""Atomic, revision-checked JSON persistence for one local user's focus data."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Callable

from pydantic import ValidationError

from .models import FocusState


class StorageError(RuntimeError):
    """Storage cannot safely read or write the focus data."""


_write_lock = RLock()


class JsonStore:
    """Read and atomically update focus data at a configurable local path."""

    def __init__(self, path: str | Path | None = None):
        configured = path or os.environ.get("FOCUS_DATA_PATH")
        project_root = Path(__file__).resolve().parents[1]
        self.path = Path(configured) if configured else project_root / "data" / "focus.json"
        if not self.path.is_absolute():
            self.path = project_root / self.path

    def load(self) -> FocusState:
        if not self.path.exists():
            return FocusState()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return FocusState.model_validate(data)
        except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
            raise StorageError(f"Cannot safely load focus data from {self.path}: {exc}") from exc

    def update(self, change: Callable[[FocusState], None]) -> FocusState:
        """Apply a change to the latest revision and replace the JSON atomically."""
        with _write_lock:
            state = self.load()
            original_revision = state.revision
            change(state)
            try:
                state.revision = original_revision + 1
                state = FocusState.model_validate(state.model_dump(mode="python"))
                self._write(state)
            except (OSError, ValidationError, ValueError, TypeError) as exc:
                raise StorageError(f"Could not save focus data to {self.path}: {exc}") from exc
            return state

    def _write(self, state: FocusState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(state.model_dump(mode="json"), stream, indent=2, ensure_ascii=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        finally:
            temporary.unlink(missing_ok=True)
