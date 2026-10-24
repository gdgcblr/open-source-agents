"""Offline demo: replay a recorded Gemini run through the real agents, MCP server and ledger.

Only the model's choices (which tools to call, with which arguments, and the reminder
templates it wrote) come from the recording. The ledger still computes every amount,
status and policy decision live, and the number guard still checks every template.
"""

import json
from pathlib import Path

from google.genai import types

from invoice_chaser.agent import build_root_agent
from invoice_chaser.scripted_llm import ScriptedLlm, call, text

RECORDING = Path(__file__).resolve().parent / "replay" / "live_run_2026-10-24.json"


def _batch(calls: list[list[types.Part]]) -> list[types.Part]:
    """Several function calls in one model turn (as Gemini did with parallel calls)."""
    return [part for c in calls for part in c]


def load_recording() -> dict:
    return json.loads(RECORDING.read_text(encoding="utf-8"))


def build_replay_agent(recording: dict | None = None):
    rec = recording or load_recording()
    matcher = ScriptedLlm(steps=[
        _batch([call("list_unmatched_payments"), call("list_open_invoices")]),
        _batch([call("propose_match", **p) for p in rec["matcher_proposals"]]),
        text("(replayed) matching done"),
    ])
    drafter = ScriptedLlm(steps=[
        call("get_chase_list"),
        _batch([call("queue_reminder", **d) for d in rec["drafts"]]),
        text("(replayed) drafting done"),
    ])
    root = ScriptedLlm(steps=[
        call("payment_matcher", request="Match new bank payments to invoices."),
        call("reminder_drafter", request="Draft reminders for today's chase list."),
        call("run_report"),
        text(rec["root_summary"]),
    ])
    return build_root_agent(model=root, matcher_model=matcher, drafter_model=drafter)
