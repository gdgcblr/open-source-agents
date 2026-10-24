from unittest.mock import MagicMock

from rentrakshak.agent_callbacks import after_tool_callback, before_tool_callback


def _ctx(invocation_id: str = "inv-1"):
    state: dict = {}
    ctx = MagicMock()
    ctx.invocation_id = invocation_id
    ctx.state = state
    return ctx, state


def test_blocks_second_identical_tool_call():
    tool = MagicMock()
    tool.name = "build_rental_checklist_tool"
    ctx, state = _ctx()
    assert before_tool_callback(tool, {}, ctx) is None
    after_tool_callback(tool, {}, ctx, {"items": []})
    blocked = before_tool_callback(tool, {}, ctx)
    assert blocked is not None
    assert blocked["duplicate_call_blocked"] is True
    assert blocked["previous_result"] == {"items": []}


def test_new_invocation_allows_tool_again():
    tool = MagicMock()
    tool.name = "build_rental_checklist_tool"
    ctx1, _ = _ctx("inv-a")
    assert before_tool_callback(tool, {}, ctx1) is None
    ctx2, _ = _ctx("inv-b")
    assert before_tool_callback(tool, {}, ctx2) is None
