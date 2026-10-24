"""Shared memory: the context-orchestration-engine tool from this repository.

The agents never share a conversation. Everything one agent hands to the next
lives in the engine's canonical state (SQLite), written only by its reconciler and
read back only as a compiled briefing. The engine is imported, not copied, from
``tools/context-orchestration-engine`` (or from ``COE_TOOL_PATH``), appended
to ``sys.path`` so this project's own modules always win a name clash.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parents[3] / "tools" / "context-orchestration-engine"
TOOL_DIR = Path(os.environ.get("COE_TOOL_PATH") or _DEFAULT)

if not (TOOL_DIR / "context_orchestration").is_dir():
    raise ImportError(
        f"context-orchestration-engine not found at {TOOL_DIR}. Run from a full clone of "
        "this repository, or set COE_TOOL_PATH to the tool's folder."
    )
if str(TOOL_DIR) not in sys.path:
    sys.path.append(str(TOOL_DIR))

from context_orchestration.contracts import WorkerConfig  # noqa: E402
from context_orchestration.compiler import ContextCompiler  # noqa: E402
from context_orchestration.orchestrator import Orchestrator, RunSummary, TurnResult  # noqa: E402
from context_orchestration.store import SQLiteStore  # noqa: E402
from context_orchestration.worker import SYSTEM_PROMPT  # noqa: E402

__all__ = [
    "ContextCompiler",
    "Orchestrator",
    "RunSummary",
    "SQLiteStore",
    "SYSTEM_PROMPT",
    "TOOL_DIR",
    "TurnResult",
    "WorkerConfig",
]
