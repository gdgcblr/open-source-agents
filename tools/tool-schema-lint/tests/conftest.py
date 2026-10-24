import copy
import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[1]
EXAMPLES = PROJECT_DIR / "examples"
sys.path.insert(0, str(PROJECT_DIR))

from tool_schema_lint import lint, load_tools  # noqa: E402
from tool_schema_lint.models import TARGETS  # noqa: E402

# A tool that is clean under every target. Rule tests mutate a copy of it.
GOOD_TOOL = {
    "name": "get_weather",
    "description": (
        "Get the current weather for a city. Use it when the user asks about temperature or rain. "
        "Returns the temperature and a short summary."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "City name, e.g. Bengaluru"},
            "unit": {
                "type": "string",
                "enum": ["celsius", "fahrenheit"],
                "description": "Temperature unit to report",
            },
        },
        "required": ["city", "unit"],
        "additionalProperties": False,
    },
}


def good_tool() -> dict:
    return copy.deepcopy(GOOD_TOOL)


def rule_ids(doc, targets=None, **kwargs) -> list[str]:
    return [f.rule_id for f in lint(load_tools(doc), targets, **kwargs).findings]


@pytest.fixture
def all_targets():
    return list(TARGETS)
