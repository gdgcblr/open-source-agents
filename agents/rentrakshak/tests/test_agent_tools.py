from google.adk.tools.function_tool import FunctionTool

from rentrakshak.agent import root_agent
from rentrakshak.tools.registry import ALL_TOOL_FUNCTIONS, generate_rental_safety_report_tool


def test_root_agent_has_tools():
    assert root_agent.name == "rentrakshak"
    assert len(root_agent.tools) >= 10


def test_tool_functions_registered():
    assert len(ALL_TOOL_FUNCTIONS) == 13


def test_safety_report_tool_offline():
    out = generate_rental_safety_report_tool(
        listing_text="Pay token before viewing. Send OTP. Koramangala 1 BHK rent 10000",
        chat_text="",
    )
    assert out["risk_category"] in {
        "critical_warning",
        "high_concern",
        "needs_verification",
        "low_concern",
    }
    assert out["findings"]


def test_function_tool_wrap():
    ft = FunctionTool(generate_rental_safety_report_tool)
    assert ft.name == "generate_rental_safety_report_tool"
