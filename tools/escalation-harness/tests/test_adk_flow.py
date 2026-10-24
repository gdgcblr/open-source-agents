"""End-to-end through a real ADK runner, with a scripted model so no API key is needed."""

import asyncio
from typing import Any

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types

from refund_agent import store
from refund_agent.agent import build_agent, new_harness


class ScriptedLlm(BaseLlm):
    """Returns pre-written responses in order, standing in for Gemini."""

    script: list[Any] = []
    requests: list[Any] = []

    async def generate_content_async(self, llm_request, stream=False):
        self.requests.append(llm_request)
        yield self.script.pop(0)


def call(name, **args):
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name=name, args=args))]))


def say(text):
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))


def run(model, harness, *messages):
    async def go():
        store.reset()
        runner = InMemoryRunner(agent=build_agent(harness, model), app_name="test")
        session = await runner.session_service.create_session(app_name="test", user_id="u", state={"customer_id": "C-101"})
        events = []
        for text in messages:
            content = types.Content(role="user", parts=[types.Part(text=text)])
            events += [e async for e in runner.run_async(user_id="u", session_id=session.id, new_message=content)]
        return session, events

    return asyncio.run(go())


def tool_responses(events):
    return [r.response for e in events for r in e.get_function_responses()]


def test_guessed_order_is_blocked_and_the_model_is_told_to_ask():
    model = ScriptedLlm(
        model="scripted",
        script=[call("list_orders"), call("issue_refund", order_id="ORD-1003", amount=18999, reason="damaged", destination="original_payment"), say("Which order?")],
    )
    harness = new_harness()
    session, events = run(model, harness, "Refund my order, it arrived damaged.")

    assert store.ledger() == []
    blocked = tool_responses(events)[-1]
    assert blocked["harness_blocked"] and blocked["decision"] == "clarify"
    assert [d["decision"] for d in harness.decisions(session.id)] == ["act", "clarify"]


def test_same_guess_goes_through_without_the_harness():
    model = ScriptedLlm(
        model="scripted",
        script=[call("list_orders"), call("issue_refund", order_id="ORD-1003", amount=18999, reason="damaged", destination="original_payment"), say("Done!")],
    )
    run(model, None, "Refund my order, it arrived damaged.")
    assert [e["order_id"] for e in store.ledger()] == ["ORD-1003"]


def test_answered_question_lets_the_refund_through():
    model = ScriptedLlm(
        model="scripted",
        script=[
            call("issue_refund", order_id="ORD-1002", amount=2499, reason="damaged", destination="original_payment"),
            say("Which order?"),
            call("issue_refund", order_id="ORD-1002", amount=2499, reason="damaged", destination="original_payment"),
            say("Refunded."),
        ],
    )
    harness = new_harness()
    session, _ = run(model, harness, "Refund my order", "It's ORD-1002")
    assert [d["decision"] for d in harness.decisions(session.id)] == ["clarify", "act"]
    assert [e["order_id"] for e in store.ledger()] == ["ORD-1002"]


def test_large_refund_escalates_with_a_full_handoff_packet():
    model = ScriptedLlm(
        model="scripted",
        script=[call("issue_refund", order_id="ORD-1003", amount=18999, reason="stain", destination="original_payment"), say("A teammate will follow up.")],
    )
    harness = new_harness()
    run(model, harness, "Refund ORD-1003, the lehenga had a stain.")

    assert store.ledger() == []
    (packet,) = harness.handoffs
    assert packet["customer_id"] == "C-101"
    assert packet["customer_intent"] == "Refund ORD-1003, the lehenga had a stain."
    assert packet["proposed_action"]["args"]["amount"] == 18999
    assert packet["rule"].startswith("escalate_if:amount")


def test_model_escalation_packet_uses_the_tools_ticket():
    model = ScriptedLlm(model="scripted", script=[call("escalate_to_human", reason="Customer is upset"), say("A teammate will follow up.")])
    harness = new_harness()
    run(model, harness, "Nothing you say is helping.")

    (packet,) = harness.handoffs
    (escalation,) = store.ledger()
    assert packet["ticket_id"] == escalation["ticket_id"]


def test_gate_and_model_escalating_together_makes_one_ticket():
    # Seen in a live run: the gate escalated a large refund, then the model escalated again.
    model = ScriptedLlm(
        model="scripted",
        script=[
            call("issue_refund", order_id="ORD-1003", amount=18999, reason="stain", destination="original_payment"),
            call("escalate_to_human", reason="Refund above the limit"),
            say("A teammate will follow up."),
        ],
    )
    harness = new_harness()
    _, events = run(model, harness, "Refund ORD-1003, the lehenga had a stain.")

    gate_response, model_response = tool_responses(events)
    assert len(harness.handoffs) == 1
    assert store.ledger() == []
    assert gate_response["ticket_id"] == model_response["ticket_id"] == harness.handoffs[0]["ticket_id"]


def test_legal_threat_reaches_a_human_before_the_model_runs():
    model = ScriptedLlm(model="scripted", script=[say("should never be used")])
    harness = new_harness()
    session, events = run(model, harness, "Cancel ORD-1004 now or I'm taking you to consumer court.")

    assert model.requests == []
    assert store.ledger() == []
    assert harness.decisions(session.id)[0]["rule"] == "phrase:legal_threat"
    assert "ticket" in events[-1].content.parts[0].text
