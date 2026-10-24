"""Provider-neutral rules: structural correctness and description quality."""

from __future__ import annotations

import re
from collections.abc import Iterable

from ..loader import pointer
from ..models import FORMAT_ANTHROPIC, FORMAT_GEMINI, FORMAT_MCP, Severity, ToolDef
from ..schema_walk import resolve_ref, walk
from . import Issue, rule, set_rule

JSON_SCHEMA = "JSON Schema 2020-12 validation vocabulary (json-schema.org)"
MCP_TOOL = "MCP spec 2025-11-25, server/tools 'Tool' data type"
ANTHROPIC_GUIDE = "Anthropic docs, 'Define tools' best practices"

JSON_TYPES = {"string", "number", "integer", "boolean", "object", "array", "null"}
MIN_DESCRIPTION_CHARS = 40
PLACEHOLDER = re.compile(
    r"^\s*(todo|tbd|fixme|xxx|n/?a|none|description|desc|lorem ipsum.*|\.+|-+)\s*[.!]?\s*$", re.IGNORECASE
)


def schema_path(tool: ToolDef, segments: tuple) -> str:
    return tool.schema_location + pointer(*segments)


def _is_object_schema(schema: dict) -> bool:
    t = schema.get("type")
    return t == "object" or (isinstance(t, list) and "object" in t) or "properties" in schema


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


@rule("G001", Severity.ERROR, "Tool has a non-empty string name", MCP_TOOL)
def missing_name(tool: ToolDef) -> Iterable[Issue]:
    if not isinstance(tool.name, str) or not tool.name.strip():
        yield Issue(tool.body_location + "/name", "tool has no name",
                    "Every provider requires a unique, non-empty tool name.")


@set_rule("G002", Severity.ERROR, "Tool names are unique", MCP_TOOL)
def duplicate_names(tools: list[ToolDef]) -> Iterable[Issue]:
    seen: dict[str, ToolDef] = {}
    for tool in tools:
        if not isinstance(tool.name, str):
            continue
        if tool.name in seen:
            yield Issue(tool.body_location + "/name",
                        f"duplicate tool name '{tool.name}' (first defined at {seen[tool.name].location})",
                        "Rename one of the tools; models select tools by name.", tool)
        else:
            seen[tool.name] = tool


@rule("G003", Severity.WARNING, "Tool has a description", ANTHROPIC_GUIDE)
def missing_description(tool: ToolDef) -> Iterable[Issue]:
    if not isinstance(tool.description, str) or not tool.description.strip():
        yield Issue(tool.body_location + "/description", "tool has no description",
                    "Describe what the tool does, when to use it, and what it returns. "
                    "The model relies on this text to choose the tool.")


@rule("G004", Severity.WARNING, f"Tool description is at least {MIN_DESCRIPTION_CHARS} characters", ANTHROPIC_GUIDE)
def short_description(tool: ToolDef) -> Iterable[Issue]:
    d = tool.description
    if not isinstance(d, str) or not d.strip() or PLACEHOLDER.match(d):
        return  # reported by G003 / G005
    if isinstance(tool.name, str) and _normalize(d) == _normalize(tool.name):
        return  # reported by G005
    if len(d.strip()) < MIN_DESCRIPTION_CHARS:
        yield Issue(tool.body_location + "/description",
                    f"description is only {len(d.strip())} characters: \"{d.strip()}\"",
                    "Say when the tool should (and should not) be used and what it returns.")


@rule("G005", Severity.WARNING, "Descriptions are not placeholders or a copy of the name", ANTHROPIC_GUIDE)
def placeholder_description(tool: ToolDef) -> Iterable[Issue]:
    d = tool.description
    if isinstance(d, str) and d.strip():
        if PLACEHOLDER.match(d):
            yield Issue(tool.body_location + "/description", f"description looks like a placeholder: \"{d.strip()}\"",
                        "Replace it with a real explanation of the tool.")
        elif isinstance(tool.name, str) and _normalize(d) == _normalize(tool.name):
            yield Issue(tool.body_location + "/description", "description only repeats the tool name",
                        "Explain the behaviour instead of restating the name.")
    for node in walk(tool.schema):
        if node.property_name is None or not isinstance(node.schema, dict):
            continue
        pd = node.schema.get("description")
        if isinstance(pd, str) and pd.strip() and (
            PLACEHOLDER.match(pd) or _normalize(pd) == _normalize(node.property_name)
        ):
            yield Issue(schema_path(tool, node.segments) + "/description",
                        f"parameter '{node.property_name}' has a placeholder description: \"{pd.strip()}\"",
                        "Describe the expected value, its format, and an example.")


@rule("G006", Severity.ERROR, "Parameter schema exists and is an object schema", MCP_TOOL)
def root_schema(tool: ToolDef) -> Iterable[Issue]:
    s = tool.schema
    if s is None:
        # Parameters are optional for OpenAI and Gemini, but required by MCP and Anthropic.
        if tool.source_format in (FORMAT_MCP, FORMAT_ANTHROPIC):
            yield Issue(tool.schema_location, f"tool has no '{tool.schema_key}'",
                        "Use {\"type\": \"object\", \"additionalProperties\": false} for a tool without parameters.")
        return
    if not isinstance(s, dict):
        yield Issue(tool.schema_location, f"'{tool.schema_key}' must be a JSON object, got {type(s).__name__}")
        return
    t = s.get("type")
    if not (isinstance(t, str) and t.lower() == "object"):
        yield Issue(tool.schema_location + "/type",
                    f"root schema type must be \"object\", got {t!r}" if t is not None
                    else "root schema has no \"type\": \"object\"",
                    "Tool arguments are always a JSON object; set \"type\": \"object\" at the root.")


@rule("G007", Severity.ERROR, "Keywords have the correct JSON shape", JSON_SCHEMA)
def malformed_keywords(tool: ToolDef) -> Iterable[Issue]:
    for node in walk(tool.schema):
        s = node.schema
        if not isinstance(s, dict):
            # Booleans are valid JSON Schema subschemas (true = anything, false = nothing).
            if node.segments and not isinstance(s, bool):  # the root is handled by G006
                yield Issue(schema_path(tool, node.segments),
                            f"subschema must be an object, got {type(s).__name__}")
            continue
        here = schema_path(tool, node.segments)
        if "properties" in s and not isinstance(s["properties"], dict):
            yield Issue(here + "/properties", "'properties' must be an object mapping names to schemas")
        req = s.get("required")
        if req is not None:
            if not isinstance(req, list) or not all(isinstance(r, str) for r in req):
                yield Issue(here + "/required", "'required' must be an array of property-name strings")
            elif len(set(req)) != len(req):
                yield Issue(here + "/required", "'required' lists the same property more than once")
        if "enum" in s and not isinstance(s["enum"], list):
            yield Issue(here + "/enum", "'enum' must be an array")
        if "items" in s and not isinstance(s["items"], (dict, list)):
            yield Issue(here + "/items", "'items' must be a schema object")
        if "description" in s and not isinstance(s["description"], str):
            yield Issue(here + "/description", "'description' must be a string")


@rule("G008", Severity.ERROR, "Every 'required' entry is a defined property", JSON_SCHEMA)
def required_undefined(tool: ToolDef) -> Iterable[Issue]:
    for node in walk(tool.schema):
        s = node.schema
        if not isinstance(s, dict) or not isinstance(s.get("required"), list):
            continue
        props: dict = s["properties"] if isinstance(s.get("properties"), dict) else {}
        # With additionalProperties allowed, a required-but-undeclared name is legal JSON
        # Schema, but no model will know it exists. Report it either way.
        for name in s["required"]:
            if isinstance(name, str) and name not in props:
                yield Issue(schema_path(tool, node.segments) + "/required",
                            f"'{name}' is required but not defined in 'properties'",
                            "Add the property definition or remove it from 'required' (check for typos).")


@rule("G009", Severity.ERROR, "'type' values are valid JSON Schema types", JSON_SCHEMA)
def invalid_type(tool: ToolDef) -> Iterable[Issue]:
    # Gemini's native `parameters` Schema accepts upper-case enum names such as "STRING".
    case_insensitive = tool.source_format == FORMAT_GEMINI and tool.schema_key == "parameters"
    for node in walk(tool.schema):
        s = node.schema
        if not isinstance(s, dict) or "type" not in s:
            continue
        values = s["type"] if isinstance(s["type"], list) else [s["type"]]
        for v in values:
            ok = isinstance(v, str) and ((v.lower() if case_insensitive else v) in JSON_TYPES)
            if not ok:
                yield Issue(schema_path(tool, node.segments) + "/type", f"unknown type {v!r}",
                            "Use one of: " + ", ".join(sorted(JSON_TYPES)) + ".")


@rule("G010", Severity.WARNING, "Parameters declare a type", JSON_SCHEMA)
def missing_type(tool: ToolDef) -> Iterable[Issue]:
    for node in walk(tool.schema):
        s = node.schema
        if node.property_name is None or not isinstance(s, dict):
            continue
        if not any(k in s for k in ("type", "anyOf", "oneOf", "allOf", "$ref", "enum", "const")):
            yield Issue(schema_path(tool, node.segments),
                        f"parameter '{node.property_name}' has no type",
                        "Without a type the model has to guess the value's shape.")


@rule("G011", Severity.WARNING, "Parameters have descriptions", ANTHROPIC_GUIDE)
def property_description(tool: ToolDef) -> Iterable[Issue]:
    for node in walk(tool.schema):
        s = node.schema
        if node.property_name is None or not isinstance(s, dict) or "$ref" in s:
            continue
        d = s.get("description")
        if not isinstance(d, str) or not d.strip():
            yield Issue(schema_path(tool, node.segments),
                        f"parameter '{node.property_name}' has no description",
                        "Explain what the value means, its format, and give an example.")


@rule("G012", Severity.ERROR, "'enum' arrays are non-empty and have no duplicates", JSON_SCHEMA)
def bad_enum(tool: ToolDef) -> Iterable[Issue]:
    for node in walk(tool.schema):
        s = node.schema
        if not isinstance(s, dict) or not isinstance(s.get("enum"), list):
            continue
        values = s["enum"]
        here = schema_path(tool, node.segments) + "/enum"
        if not values:
            yield Issue(here, "'enum' is empty, so no value can ever be valid")
            continue
        seen: list = []
        for v in values:
            if v in seen and not isinstance(v, bool):
                yield Issue(here, f"'enum' contains {v!r} more than once")
                break
            seen.append(v)


@rule("G013", Severity.WARNING, "'default' is one of the 'enum' values", JSON_SCHEMA)
def default_not_in_enum(tool: ToolDef) -> Iterable[Issue]:
    for node in walk(tool.schema):
        s = node.schema
        if (isinstance(s, dict) and isinstance(s.get("enum"), list) and "default" in s
                and s["default"] not in s["enum"]):
            yield Issue(schema_path(tool, node.segments) + "/default",
                        f"default {s['default']!r} is not one of the enum values")


@rule("G014", Severity.WARNING, "Array parameters define 'items'", JSON_SCHEMA)
def array_items(tool: ToolDef) -> Iterable[Issue]:
    for node in walk(tool.schema):
        s = node.schema
        if not isinstance(s, dict):
            continue
        t = s.get("type")
        is_array = (isinstance(t, str) and t.lower() == "array") or (isinstance(t, list) and "array" in t)
        if is_array and "items" not in s and "prefixItems" not in s:
            yield Issue(schema_path(tool, node.segments), "array has no 'items' schema",
                        "Describe the element type; some providers reject arrays without 'items'.")


@rule("G015", Severity.ERROR, "Every '$ref' resolves inside the schema", JSON_SCHEMA)
def unresolved_ref(tool: ToolDef) -> Iterable[Issue]:
    for node in walk(tool.schema):
        s = node.schema
        if isinstance(s, dict) and "$ref" in s:
            ref = s["$ref"]
            if not isinstance(ref, str):
                yield Issue(schema_path(tool, node.segments) + "/$ref", "'$ref' must be a string")
                continue
            ok, reason = resolve_ref(tool.schema, ref)
            if not ok:
                yield Issue(schema_path(tool, node.segments) + "/$ref", f"cannot resolve '{ref}': {reason}",
                            "Inline the definition or add it under '$defs'.")


def object_nodes(tool: ToolDef):
    """Yield walker nodes that describe JSON objects. Shared by provider rule modules."""
    for node in walk(tool.schema):
        if isinstance(node.schema, dict) and _is_object_schema(node.schema):
            yield node
