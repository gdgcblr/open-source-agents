"""Flight recorder: conversation events from the orchestrator, tool events from the proxy,
merged into one timeline (trace.jsonl, event schema v1)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from murphy.secrets import redact

EVENT_VERSION = 1


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, default=str))


class Recorder:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.path = run_dir / "conversation.jsonl"
        self.seq = 0

    def log(self, kind: str, **fields) -> None:
        self.seq += 1
        event = {"v": EVENT_VERSION, "kind": kind, "ts": time.time(), "seq": self.seq, **fields}
        with self.path.open("a") as f:
            f.write(json.dumps(event) + "\n")

    def tool_events(self) -> list[dict]:
        return read_jsonl(self.run_dir / "tools.jsonl")

    def merge(self) -> list[dict]:
        """Returns raw events (for checks) and persists redacted copies: trace.jsonl, tools.jsonl, conversation.jsonl."""
        conversation, tools = read_jsonl(self.path), self.tool_events()
        events = sorted(conversation + tools, key=lambda e: (e["ts"], e["kind"] != "user"))
        for name, rows in (("trace.jsonl", events), ("tools.jsonl", tools), ("conversation.jsonl", conversation)):
            if rows or name == "trace.jsonl":
                with (self.run_dir / name).open("w") as f:
                    for e in rows:
                        f.write(json.dumps(redact(e)) + "\n")
        return events
