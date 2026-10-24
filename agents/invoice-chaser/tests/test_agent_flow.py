"""Agent flow tests: real ADK runner + real MCP server subprocess + scripted model.

These check that components talk to each other correctly (routing, allow-lists,
run_id tagging, error handling) without calling Gemini.
"""

import asyncio
import json

import pytest

from ledger import Ledger
from tests.conftest import GOOD_BODY, GOOD_SUBJECT, SAMPLE
from tests.mock_llm import ScriptedLlm, call, text, tool_responses

pytest.importorskip("google.adk")


@pytest.fixture
def env(tmp_path, monkeypatch, config):
    db = tmp_path / "ledger.db"
    owner = Ledger(db, config)
    owner.import_clients(str(SAMPLE / "clients.csv"))
    owner.import_invoices(str(SAMPLE / "invoices.csv"))
    owner.import_payments(str(SAMPLE / "bank_statement.csv"))
    owner.close()
    monkeypatch.setenv("INVOICE_CHASER_DB", str(db))
    monkeypatch.setenv("INVOICE_CHASER_TODAY", "2026-10-24")
    monkeypatch.setenv("GOOGLE_API_KEY", "not-used-by-scripted-model")
    return db


def run(agent, message: str) -> dict:
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    async def go():
        runner = InMemoryRunner(agent=agent, app_name="test")
        session = await runner.session_service.create_session(app_name="test", user_id="priya")
        events = []
        try:
            async for ev in runner.run_async(
                    user_id="priya", session_id=session.id,
                    new_message=types.Content(role="user", parts=[types.Part.from_text(text=message)])):
                events.append(ev)
            state = (await runner.session_service.get_session(
                app_name="test", user_id="priya", session_id=session.id)).state
        finally:
            await runner.close()
        final = [e for e in events if e.author == "invoice_chaser" and e.content and e.content.parts
                 and e.content.parts[0].text]
        return {"events": events, "state": state,
                "final_text": final[-1].content.parts[0].text if final else None}

    return asyncio.run(go())


def last_response(name: str):
    """Step that inspects the latest response from tool `name` (for assertions)."""
    def step(req):
        responses = [r for r in tool_responses(req) if r["name"] == name]
        step.seen = responses[-1]["response"] if responses else None
        return text("noted")
    return step


def parse(resp) -> dict:
    """MCP tool results arrive as {'content': [{'text': json}], ...} or a plain dict."""
    if isinstance(resp, dict) and "content" in resp:
        return json.loads(resp["content"][0]["text"])
    if isinstance(resp, dict) and "result" in resp and isinstance(resp["result"], str):
        return json.loads(resp["result"])
    return resp


def build(root_steps, matcher_steps=(), drafter_steps=()):
    from invoice_chaser.agent import build_root_agent
    root = ScriptedLlm(steps=list(root_steps))
    matcher = ScriptedLlm(steps=list(matcher_steps))
    drafter = ScriptedLlm(steps=list(drafter_steps))
    return build_root_agent(model=root, matcher_model=matcher, drafter_model=drafter), root, matcher, drafter


def test_full_chase_run(env, config):
    agent, root, matcher, drafter = build(
        root_steps=[
            call("payment_matcher", request="match new payments"),
            call("reminder_drafter", request="draft today's reminders"),
            call("run_report", run_id="model-chosen-id"),
            text("Summary written by model"),
        ],
        matcher_steps=[
            call("list_unmatched_payments"),
            call("propose_match", payment_id=1, invoice_ids=["INV-2026-001"], name_confidence=0.97,
                 reason="ACME DESIGN PVT LTD"),
            call("propose_match", payment_id=5, invoice_ids=["INV-2026-012"], name_confidence=0.95,
                 reason="GREEN LEAF FOODS"),
            text("1: Acme AUTO_APPLIED; 5: GreenLeaf AUTO_APPLIED"),
        ],
        drafter_steps=[
            call("get_chase_list"),
            call("queue_reminder", invoice_id="INV-2026-004", tone_level=2, language="hinglish",
                 subject_template=GOOD_SUBJECT, body_template=GOOD_BODY),
            text("INV-2026-004 QUEUED"),
        ],
    )
    result = run(agent, "run today's chase")
    run_id = result["state"]["run_id"]
    assert result["final_text"] == "Summary written by model"

    led = Ledger(env, config)
    assert led.get_invoice("INV-2026-001")["invoice"]["status"] == "PAID"
    assert led.get_invoice("INV-2026-012")["invoice"]["status"] == "PAID"
    queued = led.list_reminders("QUEUED")["reminders"]
    assert [r["invoice_id"] for r in queued] == ["INV-2026-004"]
    assert "₹18,000" in queued[0]["body"]

    # Every agent write is tagged with the session's run_id (not one the model chose).
    events = led.get_audit_log(run_id=run_id)["events"]
    assert {e["action"] for e in events} == {"propose_match", "apply_allocation", "queue_reminder"}
    assert {e["actor"] for e in events} == {"agent"}
    assert led.get_audit_log(run_id="model-chosen-id")["events"] == []
    assert led.check_invariants()["ok"]

    # The root model saw the run report for its own run.
    report = parse([r for r in tool_responses(root.requests[-1]) if r["name"] == "run_report"][-1]["response"])
    assert (report["run_id"], report["payments_auto_matched"], report["reminders_queued"]) == (run_id, 2, 1)


def test_ledger_rejection_reaches_the_model_and_nothing_is_written(env, config):
    checker = last_response("queue_reminder")
    agent, *_ = build(
        root_steps=[call("reminder_drafter", request="draft"), text("ok")],
        drafter_steps=[
            call("queue_reminder", invoice_id="INV-2026-004", tone_level=2, language="en",
                 subject_template="Reminder", body_template="Please pay 18000 for {invoice_no} {amount_due}"),
            checker,
        ],
    )
    run(agent, "draft reminders")
    seen = parse(checker.seen)
    assert seen["error_code"] == "RENDER_REJECTED"
    assert any("digits" in p for p in seen["problems"])
    assert Ledger(env, config).list_reminders("QUEUED")["reminders"] == []


def test_subagent_cannot_use_tools_outside_its_allow_list(env, config):
    """The matcher hallucinates a drafter tool; the run must not crash or write anything."""
    agent, root, matcher, _ = build(
        root_steps=[call("payment_matcher", request="match"), text("ok")],
        matcher_steps=[
            call("queue_reminder", invoice_id="INV-2026-004", tone_level=2, language="en",
                 subject_template=GOOD_SUBJECT, body_template=GOOD_BODY),
            text("tried"),
        ],
    )
    result = run(agent, "match payments")
    assert result["final_text"] == "ok"
    seen = tool_responses(matcher.requests[-1])
    assert seen[-1]["response"]["error_code"] == "TOOL_NOT_ALLOWED"
    assert Ledger(env, config).list_reminders("QUEUED")["reminders"] == []


def test_owner_only_actions_are_not_exposed_to_agents():
    from invoice_chaser.agent import ALLOWED_TOOLS
    from ledger import mcp_server
    exposed = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    forbidden = {"confirm_match", "reject_match", "approve_reminder", "skip_reminder", "mark_sent",
                 "set_invoice_hold", "import_clients", "import_invoices", "import_payments"}
    assert not exposed & forbidden
    assert set().union(*ALLOWED_TOOLS.values()) <= exposed


def test_injection_in_narration_cannot_mark_invoices_paid(env, config):
    """Even if the model obeys the injected narration, the ledger only records a proposal."""
    agent, *_ = build(
        root_steps=[call("payment_matcher", request="match"), text("ok")],
        matcher_steps=[
            call("propose_match", payment_id=7, invoice_ids=["INV-2026-002"], name_confidence=1.0,
                 reason="narration says mark all invoices paid"),
            call("propose_match", payment_id=7,
                 invoice_ids=["INV-2026-004", "INV-2026-005", "INV-2026-007"], name_confidence=1.0,
                 reason="narration says mark all invoices paid"),
            text("done"),
        ],
    )
    run(agent, "match payments")
    led = Ledger(env, config)
    statuses = {i["invoice_id"]: i["status"] for i in led.list_open_invoices()["invoices"]}
    assert statuses["INV-2026-002"] == "OVERDUE"  # ₹1,000 vs ₹30,000 -> partial, needs owner
    assert "PAID" not in statuses.values()
    pending = led.list_pending_matches()["proposals"]
    assert [p["invoice_ids"] for p in pending] == [["INV-2026-002"]]  # multi-client call rejected
    assert led.check_invariants()["ok"]
