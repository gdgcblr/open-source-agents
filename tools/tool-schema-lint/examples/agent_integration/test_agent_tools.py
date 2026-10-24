"""Copy this test into your own agent to fail fast when a tool definition breaks.

Run from tools/tool-schema-lint:  python -m pytest examples/agent_integration
"""

from agent_tools import TOOLS

from tool_schema_lint import Severity, lint, load_tools

# The providers this agent must work with.
TARGETS = ["openai-strict", "gemini"]


def test_tool_definitions_are_valid_for_every_target_provider():
    result = lint(load_tools(TOOLS), targets=TARGETS)
    errors = [f for f in result.findings if f.severity == Severity.ERROR]
    assert not errors, "\n".join(f"{f.rule_id} {f.tool} {f.path}: {f.message}" for f in errors)


def test_tool_definitions_stay_within_context_budget():
    result = lint(load_tools(TOOLS), max_tokens=1000)
    assert not [f for f in result.findings if f.rule_id == "G016"], f"~{result.token_estimate} tokens"
