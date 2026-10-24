"""Every rule must fire on its bad case and stay silent on the shared good tool."""

import copy

import pytest
from conftest import good_tool, rule_ids

from tool_schema_lint.rules import REGISTRY


def schema(t):
    return t["inputSchema"]


def prop(t, name="city"):
    return t["inputSchema"]["properties"][name]


def nested_objects(levels: int) -> dict:
    """A root object whose properties nest `levels` objects deep in total."""
    inner = {"type": "string", "description": "leaf"}
    for i in range(levels):
        inner = {"type": "object", "description": f"level {i}", "properties": {"x": inner},
                 "required": ["x"], "additionalProperties": False}
    return inner


CASES = {
    "G001": (None, lambda t: t.update(name="")),
    "G003": (None, lambda t: t.pop("description")),
    "G004": (None, lambda t: t.update(description="Gets weather.")),
    "G005": (None, lambda t: t.update(description="TODO")),
    "G006": (None, lambda t: t.update(inputSchema={"type": "array", "items": {"type": "string"}})),
    "G007": (None, lambda t: schema(t).update(required="city")),
    "G008": (None, lambda t: schema(t)["required"].append("zip")),
    "G009": (None, lambda t: prop(t).update(type="text")),
    "G010": (None, lambda t: prop(t).pop("type")),
    "G011": (None, lambda t: prop(t).pop("description")),
    "G012": (None, lambda t: prop(t, "unit").update(enum=[])),
    "G013": (None, lambda t: prop(t, "unit").update(default="kelvin")),
    "G014": (None, lambda t: prop(t).update(type="array")),
    "G015": (None, lambda t: schema(t)["properties"].update(extra={"$ref": "#/$defs/Missing"})),
    "M001": (["mcp"], lambda t: t.update(name="get weather")),
    "M002": (["mcp"], lambda t: t.update(inputSchema={"type": "object"})),
    "A001": (["anthropic"], lambda t: t.update(name="weather.get")),
    "A002": (["anthropic"], lambda t: t.update(description="Get the current weather for a city by name.")),
    "O001": (["openai"], lambda t: t.update(name="x" * 65)),
    "S001": (["openai-strict"], lambda t: schema(t).pop("additionalProperties")),
    "S002": (["openai-strict"], lambda t: schema(t).update(required=["city"])),
    "S003": (["openai-strict"], lambda t: schema(t).update(anyOf=[{"required": ["city"]}])),
    "S004": (["openai-strict"], lambda t: prop(t).update({"not": {"const": "x"}})),
    "S005": (["openai-strict"], lambda t: prop(t).update(format="uri")),
    "S006": (["openai-strict"], lambda t: schema(t)["properties"].update(deep=nested_objects(11))),
    "GM001": (["gemini"], lambda t: t.update(name="1_weather")),
    "GM002": (["gemini"], lambda t: schema(t)["properties"].update({"time-range": {"type": "string",
                                                                                "description": "Window"}})),
    "GM003": (["gemini"], lambda t: schema(t).update({"$schema": "http://json-schema.org/draft-07/schema#"})),
    "GM004": (["gemini"], lambda t: prop(t).update(type=["string", "null"])),
    "GM005": (["gemini"], lambda t: prop(t, "unit").update(enum=[1, 2])),
}

SET_RULES = {"G002", "G016", "O002"}  # covered by dedicated tests below


def test_every_rule_has_a_test_case():
    assert set(REGISTRY) == set(CASES) | SET_RULES


def test_good_tool_is_clean_for_every_target(all_targets):
    assert rule_ids({"tools": [good_tool()]}, all_targets) == []


@pytest.mark.parametrize("rule_id", sorted(CASES))
def test_rule_fires_on_bad_case(rule_id):
    targets, mutate = CASES[rule_id]
    tool = good_tool()
    mutate(tool)
    assert rule_id in rule_ids({"tools": [tool]}, targets)


@pytest.mark.parametrize("rule_id", sorted(r for r, (targets, _) in CASES.items() if targets))
def test_provider_rule_is_silent_for_other_targets(rule_id):
    targets, mutate = CASES[rule_id]
    tool = good_tool()
    mutate(tool)
    others = [t for t in ("mcp", "openai", "openai-strict", "gemini", "anthropic")
              if t not in targets and not (rule_id.startswith(("O",)) and t == "openai-strict")]
    assert rule_id not in rule_ids({"tools": [tool]}, others)


def test_duplicate_tool_names():
    findings = rule_ids({"tools": [good_tool(), good_tool()]})
    assert findings.count("G002") == 1


def test_tool_count_info_for_openai():
    tools = []
    for i in range(20):
        t = good_tool()
        t["name"] = f"tool_{i}"
        tools.append(t)
    assert "O002" in rule_ids({"tools": tools}, ["openai"])
    assert "O002" not in rule_ids({"tools": tools[:19]}, ["openai"])


def test_token_budget():
    doc = {"tools": [good_tool()]}
    assert "G016" in rule_ids(doc, max_tokens=10)
    assert "G016" not in rule_ids(doc, max_tokens=10_000)
    assert "G016" not in rule_ids(doc, max_tokens=10, disabled={"G016"})


def test_disabled_rule_is_skipped():
    tool = good_tool()
    prop(tool).pop("description")
    assert "G011" not in rule_ids({"tools": [tool]}, disabled={"G011"})


def test_nesting_limit_boundary():
    ok, too_deep = good_tool(), good_tool()
    schema(ok)["properties"]["deep"] = nested_objects(9)  # root + 9 = 10 levels
    schema(too_deep)["properties"]["deep"] = nested_objects(10)  # 11 levels
    schema(ok)["required"].append("deep")
    schema(too_deep)["required"].append("deep")
    assert "S006" not in rule_ids({"tools": [ok]}, ["openai-strict"])
    assert "S006" in rule_ids({"tools": [too_deep]}, ["openai-strict"])


def test_strict_rules_follow_the_tool_strict_flag():
    params = {"type": "object", "properties": {"q": {"type": "string", "description": "Query text"}}}
    desc = "Search the product catalogue by keyword and return matching product ids."
    loose = [{"type": "function", "function": {"name": "search", "description": desc, "parameters": params}}]
    strict = copy.deepcopy(loose)
    strict[0]["function"]["strict"] = True
    assert rule_ids(loose) == []
    assert {"S001", "S002"} <= set(rule_ids(strict))


def test_recursive_ref_terminates_and_resolves():
    tool = good_tool()
    schema(tool)["properties"]["children"] = {"type": "array", "items": {"$ref": "#"},
                                              "description": "Nested items"}
    schema(tool)["required"].append("children")
    assert rule_ids({"tools": [tool]}, ["mcp", "openai-strict"]) == []


def test_external_ref_is_reported():
    tool = good_tool()
    schema(tool)["properties"]["remote"] = {"$ref": "https://example.com/schema.json"}
    assert "G015" in rule_ids({"tools": [tool]})


def test_gemini_keyword_rules_skip_parameters_json_schema():
    params = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
              "properties": {"q": {"type": ["string", "null"], "description": "Query text"}},
              "required": ["q"]}
    desc = "Search the product catalogue by keyword and return matching product ids."
    for key, expected in (("parametersJsonSchema", set()), ("parameters", {"GM003", "GM004"})):
        doc = {"functionDeclarations": [{"name": "search", "description": desc, key: params}]}
        assert set(rule_ids(doc)) == expected


def test_gemini_native_uppercase_types_are_valid():
    doc = {"functionDeclarations": [{
        "name": "search",
        "description": "Search the product catalogue by keyword and return matching product ids.",
        "parameters": {"type": "OBJECT", "properties": {"q": {"type": "STRING", "description": "Query text"}}},
    }]}
    assert rule_ids(doc) == []


def test_parameters_are_optional_for_openai_and_gemini_but_not_mcp():
    desc = "Return the current server time in UTC as an ISO 8601 string."
    assert rule_ids([{"type": "function", "function": {"name": "now", "description": desc}}]) == []
    assert rule_ids({"functionDeclarations": [{"name": "now", "description": desc}]}) == []
    mcp = {"tools": [{"name": "now", "description": desc, "inputSchema": None}]}
    assert "G006" in rule_ids(mcp)


def test_boolean_subschemas_are_valid_but_other_scalars_are_not():
    tool = good_tool()
    schema(tool)["properties"]["anything"] = True
    schema(tool)["required"].append("anything")
    assert "G007" not in rule_ids({"tools": [tool]})
    schema(tool)["properties"]["anything"] = "string"
    assert "G007" in rule_ids({"tools": [tool]})
