
"""Low-level Python call tracer used by the pytest plugin.

Records project-local function calls, returns, and exceptions without
capturing function arguments or local variable values.
"""
from __future__ import annotations

import os
import sys
import time
import threading
from pathlib import Path
from types import FrameType
from typing import Any
import uuid


class CallTracer:
    """Trace nested Python calls within the selected project directory."""

    EXCLUDED_DIRS = {
        ".venv",
        "venv",
        "env",
        "site-packages",
        ".git",
        ".pytest_cache",
        "__pycache__",
        "dist-packages",
        "ai_test_trace_analyzer",
    }

    def __init__(
        self,
        project_root: str | Path | None = None,
        max_events: int = 20_000,
        trace_id: str | None = None,
    ):
        if max_events < 1:
            raise ValueError("max_events must be >= 1")

        self.project_root = Path(project_root or os.getcwd()).resolve()
        self.max_events = max_events
        self.trace_id = trace_id or str(uuid.uuid4())

        self.events: list[dict[str, Any]] = []
        self._frame_state: dict[int, dict[str, Any]] = {}
        self._filename_cache: dict[str, bool] = {}

        self._previous_trace = None
        self._previous_thread_trace = None
        self._active = False
        self._truncated = False
        self._next_call_id = 1
        self._lock = threading.RLock()

    
    def _is_project_file(self, filename: str) -> bool:
        """Include real project source files only."""
        cached = self._filename_cache.get(filename)
        if cached is not None:
            return cached

        try:
            # Ignore interpreter-generated and frozen modules.
            if filename.startswith("<") and filename.endswith(">"):
                self._filename_cache[filename] = False
                return False

            path = Path(filename).resolve()
            relative_path = path.relative_to(self.project_root)

            excluded = {
                ".venv",
                "venv",
                "env",
                "site-packages",
                ".git",
                ".pytest_cache",
                "__pycache__",
                "dist-packages",
                "ai_test_trace_analyzer",
            }

            included = (
                path.suffix == ".py"
                and not any(part in excluded for part in relative_path.parts)
            )
        except (ValueError, OSError, RuntimeError):
            included = False

        self._filename_cache[filename] = included
        return included


    def _append(self, event_data: dict[str, Any]) -> None:
        with self._lock:
            if len(self.events) >= self.max_events:
                self._truncated = True
                return

            # Every event from this pytest execution shares one correlation ID.
            event_data.setdefault("trace_id", self.trace_id)
            self.events.append(event_data)

    def _allocate_call_id(self) -> int:
        with self._lock:
            call_id = self._next_call_id
            self._next_call_id += 1
            return call_id

    def _find_parent_call_id(self, frame: FrameType) -> int | None:
        parent_frame = frame.f_back

        while parent_frame is not None:
            state = self._frame_state.get(id(parent_frame))
            if state is not None:
                return state["call_id"]
            parent_frame = parent_frame.f_back

        return None

    def _trace(self, frame: FrameType, event: str, arg: Any):
        filename = frame.f_code.co_filename

        if not self._is_project_file(filename):
            return self._trace

        frame_id = id(frame)
        now = time.perf_counter()
        function = frame.f_code.co_name

        if event == "call":
            call_id = self._allocate_call_id()
            parent_call_id = self._find_parent_call_id(frame)

            state = {
                "call_id": call_id,
                "parent_call_id": parent_call_id,
                "start": now,
                "function": function,
            }
            self._frame_state[frame_id] = state

            try:
                relative_file = str(
                    Path(filename).resolve().relative_to(self.project_root)
                )
            except (ValueError, OSError, RuntimeError):
                relative_file = filename

            self._append({
                "event": "call",
                "call_id": call_id,
                "parent_call_id": parent_call_id,
                "function": function,
                "file": relative_file,
                "line": frame.f_code.co_firstlineno,
                "timestamp_seconds": round(now, 6),
                "thread_id": threading.get_ident(),
                "thread_name": threading.current_thread().name,
            })

        elif event == "return":
            state = self._frame_state.pop(frame_id, None)

            if state is not None:
                self._append({
                    "event": "return",
                    "call_id": state["call_id"],
                    "parent_call_id": state["parent_call_id"],
                    "function": function,
                    "duration_ms": round(
                        (now - state["start"]) * 1000, 3
                    ),
                    "timestamp_seconds": round(now, 6),
                    "thread_id": threading.get_ident(),
                })

        elif event == "exception":
            exc_type, exc_value, _traceback = arg
            state = self._frame_state.get(frame_id)

            try:
                relative_file = str(
                    Path(filename).resolve().relative_to(self.project_root)
                )
            except (ValueError, OSError, RuntimeError):
                relative_file = filename

            self._append({
                "event": "exception",
                "call_id": state["call_id"] if state else None,
                "parent_call_id": (
                    state["parent_call_id"] if state else None
                ),
                "function": function,
                "file": relative_file,
                "line": frame.f_lineno,
                "exception_type": getattr(
                    exc_type, "__name__", str(exc_type)
                ),
                "message": str(exc_value)[:500],
                "timestamp_seconds": round(now, 6),
                "thread_id": threading.get_ident(),
            })

        return self._trace

    def start(self) -> None:
        """Start tracing the current thread and subsequently created threads."""
        if self._active:
            return

        self._previous_trace = sys.gettrace()
        self._previous_thread_trace = threading.gettrace()

        sys.settrace(self._trace)
        threading.settrace(self._trace)
        self._active = True

    def stop(self) -> None:
        """Stop tracing and restore the previous trace callbacks."""
        if not self._active:
            return

        sys.settrace(self._previous_trace)
        threading.settrace(self._previous_thread_trace)

        self._active = False
        self._frame_state.clear()

    def result(self) -> dict[str, Any]:
        with self._lock:
            return {
                "trace_id": self.trace_id,
                "events": list(self.events),
                "truncated": self._truncated,
                "event_limit": self.max_events,
            }
