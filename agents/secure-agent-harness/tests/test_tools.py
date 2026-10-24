import pytest
from secure_agent_harness.tools import safe_calculate, build_tools
from secure_agent_harness.memory import MemoryStore
from secure_agent_harness.decision import LocalDecisionGate


def test_calculator_allows_basic_arithmetic():
    assert safe_calculate("19 * 23") == "437"
    assert safe_calculate("(8 + 4) / 3") == "4.0"


def test_calculator_rejects_function_calls():
    with pytest.raises(ValueError):
        safe_calculate("__import__('os').system('whoami')")


def test_tool_registry_is_explicit(tmp_path):
    memory = MemoryStore(tmp_path / "memory.sqlite3")
    tools = build_tools(memory, "alice")
    assert set(tools) == {"calculator", "get_utc_time", "remember_fact"}
    gate = LocalDecisionGate()
    assert gate.evaluate("calculator", {"expression": "2+2"}, False).verdict == "allow"
    assert gate.evaluate("shell", {"command": "whoami"}, False).verdict == "block"
