"""An offline ADK model: a ``BaseLlm`` that answers from a script.

It goes through the real ADK path (Runner, session, callbacks, function
tools), so guardrails, file tools and the engine all run for real; only the
model's text is scripted. Role comes from the system instruction, the step
from the assigned task in the briefing. Requests other than the built-in demo
get a generic answer per role.
"""

from __future__ import annotations

import json
import re
from typing import AsyncGenerator

from google.genai import types
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse

from shared_memory.protocol import (
    ARCHITECT, DEMO_REQUEST, FIX_PIPELINE, FIX_PREFIX, JUNIOR, PIPELINE, ROLES, SENIOR,
)

STORE_PY = '''import json
from pathlib import Path


class TaskStore:
    """Tasks as a JSON list of {"id", "title", "done"}."""

    def __init__(self, path="tasks.json"):
        self.path = Path(path)

    def load(self):
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, tasks):
        self.path.write_text(json.dumps(tasks, indent=2), encoding="utf-8")

    def add(self, title):
        tasks = self.load()
        task = {"id": max((t["id"] for t in tasks), default=0) + 1, "title": title, "done": False}
        tasks.append(task)
        self.save(tasks)
        return task

    def mark_done(self, task_id):
        tasks = self.load()
        for task in tasks:
            if task["id"] == task_id:
                task["done"] = True
        self.save(tasks)
'''

STORE_PY_FIXED = STORE_PY.replace(
    '''        for task in tasks:
            if task["id"] == task_id:
                task["done"] = True
        self.save(tasks)
''',
    '''        for task in tasks:
            if task["id"] == task_id:
                task["done"] = True
                self.save(tasks)
                return True
        return False
''')

CLI_PY = '''import argparse

from todo.store import TaskStore


def main(argv=None):
    parser = argparse.ArgumentParser(prog="todo")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("add").add_argument("title")
    sub.add_parser("list")
    sub.add_parser("done").add_argument("id", type=int)
    args = parser.parse_args(argv)
    store = TaskStore()

    if args.command == "add":
        task = store.add(args.title)
        print(f"added {task['id']}: {task['title']}")
    elif args.command == "list":
        for task in store.load():
            print(f"[{'x' if task['done'] else ' '}] {task['id']} {task['title']}")
    else:
        store.mark_done(args.id)
        print(f"done {args.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

CLI_PY_FIXED = CLI_PY.replace(
    '''        store.mark_done(args.id)
        print(f"done {args.id}")''',
    '''        if not store.mark_done(args.id):
            print(f"no task with id {args.id}")
            return 1
        print(f"done {args.id}")''')

TEST_PY = '''from todo.store import TaskStore


def test_add_list_done(tmp_path):
    store = TaskStore(tmp_path / "tasks.json")
    task = store.add("write tests")
    assert store.load() == [{"id": 1, "title": "write tests", "done": False}]
    assert store.mark_done(task["id"]) is True
    assert store.load()[0]["done"] is True


def test_unknown_id_is_rejected(tmp_path):
    assert TaskStore(tmp_path / "tasks.json").mark_done(99) is False
'''

UNKNOWN_ID = "done command accepts unknown task ids and reports success"
NO_TESTS = "no automated tests for the store"


def _call(name: str, **args) -> types.Part:
    return types.Part(function_call=types.FunctionCall(name=name, args=args))


def _demo(role: str, step: int, tools_done: bool) -> list[types.Part] | dict:
    """Function calls to make first, or the final claims once tools have run."""
    if role == ARCHITECT:
        return {
            "summary": "Designed a two-module CLI over a JSON file store.",
            "decisions": [
                {"decision": "Use argparse subcommands add, list and done",
                 "reason": "Standard library only; matches the three requested commands"},
                {"decision": "Store tasks as a JSON list in tasks.json with integer ids",
                 "reason": "Human-readable and needs no database"},
                {"decision": "Split into todo/store.py (persistence) and todo/cli.py (commands)",
                 "reason": "Persistence can be tested without the command line"},
            ],
            "artifacts": [{"name": "design.md", "description": "Modules, data model, command contract"}],
            "assumptions": [{"text": "Single user, single process", "reason": "Not stated otherwise"}],
            "progress": "Design complete. Nothing implemented.",
            "last_action": "Recorded the module split and data model.",
            "handoff": {"state_at_handoff": "Design fixed.",
                        "notes_for_next_worker": "Keep all file IO inside TaskStore.",
                        "recommended_next_action": "Implement todo/store.py, then todo/cli.py."},
        }
    if role == JUNIOR and step == 2:
        if not tools_done:
            return [_call("write_file", path="todo/store.py", content=STORE_PY),
                    _call("write_file", path="todo/cli.py", content=CLI_PY)]
        return {
            "summary": "Implemented the store and the CLI.",
            "decisions": [{"decision": "Switch storage to SQLite", "reason": "It would be faster"}],
            "artifacts": [{"name": "todo/store.py", "description": "TaskStore over tasks.json"},
                          {"name": "todo/cli.py", "description": "add, list, done subcommands"}],
            "progress": "Implementation written. Not reviewed.",
            "last_action": "Wrote todo/cli.py.",
            "handoff": {"state_at_handoff": "Both modules written.",
                        "notes_for_next_worker": "mark_done does not check the id exists.",
                        "recommended_next_action": "Review the implementation."},
        }
    if role == SENIOR and step == 3:
        if not tools_done:
            return [_call("list_files"), _call("read_file", path="todo/store.py"),
                    _call("read_file", path="todo/cli.py")]
        return {
            "summary": "Reviewed store and CLI against the design.",
            "issues_opened": [{"description": UNKNOWN_ID, "severity": "high"},
                              {"description": NO_TESTS, "severity": "medium"}],
            "progress": "Review done; two defects open.",
            "last_action": "Read todo/store.py and todo/cli.py.",
            "handoff": {"state_at_handoff": "Two review issues open.",
                        "notes_for_next_worker": "mark_done should report whether the id existed.",
                        "recommended_next_action": "Fix the review issues."},
        }
    if role == JUNIOR and step == 4:
        if not tools_done:
            return [_call("read_file", path="todo/store.py"),
                    _call("write_file", path="todo/store.py", content=STORE_PY_FIXED),
                    _call("write_file", path="todo/cli.py", content=CLI_PY_FIXED),
                    _call("write_file", path="tests/test_store.py", content=TEST_PY)]
        return {
            "summary": "Fixed unknown-id handling and added tests.",
            "artifacts": [{"name": "todo/store.py", "description": "mark_done returns whether it found the id"},
                          {"name": "todo/cli.py", "description": "done exits 1 for an unknown id"},
                          {"name": "tests/test_store.py", "description": "pytest tests for TaskStore"}],
            "issues_resolved": [UNKNOWN_ID, NO_TESTS],
            "progress": "Review fixes written.",
            "last_action": "Wrote tests/test_store.py.",
            "handoff": {"state_at_handoff": "Fixes in place, awaiting final review.",
                        "notes_for_next_worker": "See tests/test_store.py for the unknown-id case.",
                        "recommended_next_action": "Final review."},
        }
    # senior, final review
    if not tools_done:
        return [_call("list_files"), _call("read_file", path="todo/store.py"),
                _call("read_file", path="todo/cli.py"), _call("read_file", path="tests/test_store.py")]
    return {
        "summary": "Final review: both fixes verified in the files.",
        "issues_resolved": [UNKNOWN_ID, NO_TESTS],
        "issues_opened": [{"description": "tasks.json is written without a lock; concurrent runs can lose updates",
                           "severity": "low"}],
        "progress": "Reviewed and ready to ship for single-user use.",
        "last_action": "Read all three files.",
        "handoff": {"state_at_handoff": "Ready for single-user use.",
                    "notes_for_next_worker": "Only the low-severity locking issue remains.",
                    "recommended_next_action": "Decide whether concurrent use is in scope."},
    }


def _generic(role: str, tools_done: bool) -> list[types.Part] | dict:
    handoff = {"state_at_handoff": f"{role} turn finished (mock).",
               "notes_for_next_worker": "This is scripted mock output.",
               "recommended_next_action": "Run with --real for genuine work."}
    if role == ARCHITECT:
        return {"summary": "Mock design.", "artifacts": [{"name": "design.md", "description": "Mock design"}],
                "decisions": [{"decision": "Start with a single module", "reason": "Smallest useful step"}],
                "handoff": handoff}
    if role == JUNIOR:
        if not tools_done:
            return [_call("write_file", path="NOTES.md", content="Mock implementation notes.\n")]
        return {"summary": "Mock implementation.", "artifacts": [{"name": "NOTES.md"}], "handoff": handoff}
    if not tools_done:
        return [_call("list_files")]
    return {"summary": "Mock review.",
            "issues_opened": [{"description": "Mock run: no real implementation exists", "severity": "low"}],
            "handoff": handoff}


FIX_NOTES = (
    "Offline mock run: no real analysis or fix was made.\n"
    "Set GOOGLE_API_KEY and run again for a real fix.\n"
)


def _fix(role: str, step: int, tools_done: bool) -> list[types.Part] | dict:
    """Bug-fix mode offline: exercises clone, tools, diff and patch honestly."""
    handoff = {"state_at_handoff": f"{role} turn finished (offline mock).",
               "notes_for_next_worker": "Scripted mock output; nothing was analysed.",
               "recommended_next_action": "Run with GOOGLE_API_KEY for a real fix."}
    if role == ARCHITECT:
        if not tools_done:
            return [_call("list_files")]
        return {"summary": "Listed the repository (offline mock: no root-cause analysis).",
                "decisions": [{"decision": "Record the fix approach in FIX_NOTES.md",
                               "reason": "The offline mock cannot analyse code"}],
                "handoff": handoff}
    if role == JUNIOR and step == 2:
        if not tools_done:
            return [_call("write_file", path="FIX_NOTES.md", content=FIX_NOTES)]
        return {"summary": "Wrote FIX_NOTES.md (offline mock).",
                "artifacts": [{"name": "FIX_NOTES.md", "description": "Mock placeholder"}],
                "handoff": handoff}
    if role == SENIOR:
        if not tools_done:
            return [_call("show_diff")]
        issues = ([{"description": "Offline mock: the bug is not actually fixed", "severity": "high"}]
                  if step == 3 else [])
        return {"summary": "Read the diff (offline mock).", "issues_opened": issues, "handoff": handoff}
    if not tools_done:
        return [_call("read_file", path="FIX_NOTES.md")]
    return {"summary": "Nothing more to do offline.", "handoff": handoff}


def _system_text(llm_request: LlmRequest) -> str:
    si = llm_request.config.system_instruction if llm_request.config else None
    if isinstance(si, str):
        return si
    if si is not None and getattr(si, "parts", None):
        return "".join(p.text or "" for p in si.parts)
    return ""


class MockLlm(BaseLlm):
    model: str = "mock"

    @classmethod
    def supported_models(cls) -> list[str]:
        return [r"mock"]

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        system = _system_text(llm_request)
        role = next(r for r in ROLES if f"ROLE: {r.upper()}" in system)
        briefing = next((p.text for c in llm_request.contents if c.role == "user"
                         for p in (c.parts or []) if p.text), "")
        tools_done = any(p.function_response for c in llm_request.contents for p in (c.parts or []))
        task = re.search(r"YOUR ASSIGNED TASK\n- (.+)", briefing)
        task_text = task.group(1).strip() if task else ""
        steps = FIX_PIPELINE if FIX_PREFIX in briefing else PIPELINE
        step = next((i + 1 for i, s in enumerate(steps) if s.task == task_text), 0)

        if FIX_PREFIX in briefing:
            out = _fix(role, step, tools_done)
        elif DEMO_REQUEST in briefing and step:
            out = _demo(role, step, tools_done)
        else:
            out = _generic(role, tools_done)
        parts = out if isinstance(out, list) else [types.Part(text=json.dumps(out))]
        yield LlmResponse(content=types.Content(role="model", parts=parts))
