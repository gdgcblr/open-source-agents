import json

import pytest
from conftest import good_tool

from tool_schema_lint import loader
from tool_schema_lint.loader import load_tools, read_json
from tool_schema_lint.models import InputError

PARAMS = {"type": "object", "properties": {}}


def test_mcp_jsonrpc_response_is_unwrapped():
    tools = load_tools({"jsonrpc": "2.0", "id": 1, "result": {"tools": [good_tool()]}})
    assert len(tools) == 1
    t = tools[0]
    assert (t.source_format, t.name, t.location) == ("mcp", "get_weather", "/result/tools/0")
    assert t.schema_location == "/result/tools/0/inputSchema"


def test_mcp_plain_tools_object():
    assert load_tools({"tools": [good_tool()]})[0].source_format == "mcp"


def test_openai_chat_completions_format_and_strict_flag():
    doc = [{"type": "function", "function": {"name": "f", "parameters": PARAMS, "strict": True}}]
    t = load_tools(doc)[0]
    assert (t.source_format, t.name, t.strict) == ("openai", "f", True)
    assert t.schema_location == "/0/function/parameters"


def test_openai_responses_api_format():
    t = load_tools([{"type": "function", "name": "f", "parameters": PARAMS}])[0]
    assert (t.source_format, t.schema_location, t.strict) == ("openai", "/0/parameters", False)


def test_openai_legacy_functions_list():
    t = load_tools({"functions": [{"name": "f", "parameters": PARAMS}]})[0]
    assert t.source_format == "openai"


def test_gemini_declarations_nested_in_tools_list():
    doc = {"tools": [{"functionDeclarations": [{"name": "a", "parameters": PARAMS},
                                               {"name": "b", "parametersJsonSchema": PARAMS}]}]}
    a, b = load_tools(doc)
    assert (a.source_format, a.schema_key, a.location) == ("gemini", "parameters", "/tools/0/functionDeclarations/0")
    assert (b.source_format, b.schema_key) == ("gemini", "parametersJsonSchema")


def test_gemini_snake_case_declarations():
    t = load_tools({"function_declarations": [{"name": "a", "parameters": PARAMS}]})[0]
    assert t.source_format == "gemini"


def test_anthropic_tools_list():
    t = load_tools([{"name": "a", "description": "d", "input_schema": PARAMS}])[0]
    assert (t.source_format, t.schema_key) == ("anthropic", "input_schema")


def test_single_tool_object():
    assert load_tools(good_tool())[0].location == ""


def test_ambiguous_tool_needs_input_format():
    doc = [{"name": "a", "parameters": PARAMS}]
    with pytest.raises(InputError, match="--input-format"):
        load_tools(doc)
    assert load_tools(doc, "gemini")[0].source_format == "gemini"


@pytest.mark.parametrize("doc, message", [
    ({"tools": []}, "no tool definitions"),
    ({"tools": ["not a tool"]}, "not a JSON object"),
    ({"jsonrpc": "2.0", "error": {"code": -1}}, "no 'result'"),
    ({"something": "else"}, "unrecognized input"),
    ("just a string", "top-level JSON"),
])
def test_unrecognized_inputs(doc, message):
    with pytest.raises(InputError, match=message):
        load_tools(doc)


def test_json_pointer_escaping():
    assert loader.pointer("a/b", "c~d", 0) == "/a~1b/c~0d/0"


def test_read_json_reports_position_of_syntax_error(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text('{\n  "tools": [,]\n}', encoding="utf-8")
    with pytest.raises(InputError, match="line 2, column 13"):
        read_json(str(f))


def test_read_json_missing_file(tmp_path):
    with pytest.raises(InputError, match="file not found"):
        read_json(str(tmp_path / "missing.json"))


def test_read_json_accepts_utf8_bom(tmp_path):
    f = tmp_path / "bom.json"
    f.write_bytes(b"\xef\xbb\xbf" + json.dumps({"tools": [good_tool()]}).encode())
    assert read_json(str(f))["tools"][0]["name"] == "get_weather"


def test_read_json_rejects_non_utf8(tmp_path):
    f = tmp_path / "latin1.json"
    f.write_bytes(b'{"name": "caf\xe9"}')
    with pytest.raises(InputError, match="UTF-8"):
        read_json(str(f))


def test_read_json_rejects_extreme_nesting(tmp_path):
    f = tmp_path / "deep.json"
    f.write_text("[" * 100_000 + "]" * 100_000, encoding="utf-8")
    with pytest.raises(InputError, match="nested too deeply"):
        read_json(str(f))


def test_read_json_rejects_oversized_file(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "MAX_INPUT_BYTES", 10)
    f = tmp_path / "big.json"
    f.write_text(json.dumps({"tools": [good_tool()]}), encoding="utf-8")
    with pytest.raises(InputError, match="larger than"):
        read_json(str(f))
