from unittest.mock import MagicMock

from rentrakshak.agent_callbacks import (
    after_tool_callback,
    before_agent_callback,
    before_tool_callback,
)


def _ctx(invocation_id: str = "inv-1", session_id: str = "sess-1"):
    state: dict = {}
    ctx = MagicMock()
    ctx.invocation_id = invocation_id
    sess = MagicMock()
    sess.id = session_id
    ctx.session = sess
    ctx.state = state
    ctx.get_invocation_context = MagicMock(return_value=MagicMock(invocation_id=invocation_id))
    return ctx, state


def test_blocks_second_identical_tool_call():
    tool = MagicMock()
    tool.name = "analyze_rental_listing"
    cb = MagicMock()
    cb.session = MagicMock(id="sess-1")
    cb.invocation_id = "inv-1"
    before_agent_callback(cb)

    ctx, _ = _ctx()
    assert before_tool_callback(tool, {}, ctx) is None
    after_tool_callback(tool, {}, ctx, {"items": []})
    blocked = before_tool_callback(tool, {}, ctx)
    assert blocked is not None
    assert blocked["duplicate_call_blocked"] is True
    assert blocked["previous_result"]["items"] == []


def test_new_invocation_allows_tool_again():
    tool = MagicMock()
    tool.name = "analyze_rental_listing"
    cb = MagicMock()
    cb.session = MagicMock(id="sess-1")
    cb.invocation_id = "inv-a"
    before_agent_callback(cb)

    ctx1, _ = _ctx("inv-a")
    assert before_tool_callback(tool, {}, ctx1) is None

    cb.invocation_id = "inv-b"
    before_agent_callback(cb)
    ctx2, _ = _ctx("inv-b")
    assert before_tool_callback(tool, {}, ctx2) is None
