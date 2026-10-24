"""Gemini API function-declaration rules.

Gemini accepts parameters in two fields of a FunctionDeclaration:

* `parameters`           - Gemini's own `Schema` object (an OpenAPI 3.0 subset)
* `parametersJsonSchema` - standard JSON Schema

The keyword rules (GM003-GM005) describe the `Schema` object, so they are skipped for
tools read from `parametersJsonSchema`. Tools from other formats linted with
`--target gemini` are assumed to be sent as `parameters`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from ..models import FORMAT_GEMINI, Severity, ToolDef
from ..schema_walk import walk
from . import Issue, rule
from .general import schema_path

GEMINI_DECL = "google-genai SDK types.FunctionDeclaration (python-genai@6bd3d40, 2026-10-23)"
GEMINI_SCHEMA = "google-genai SDK types.Schema fields (python-genai@6bd3d40, 2026-10-23)"

_TARGET = [FORMAT_GEMINI]
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:-]{0,127}$")
_PARAM = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")

# Fields of the Gemini `Schema` message, in their JSON (camelCase) and SDK (snake_case)
# spellings. `$ref`/`$defs` are tolerated as well because the SDK resolves them.
SCHEMA_FIELDS = {
    "type", "format", "title", "description", "nullable", "enum", "default", "example",
    "items", "minItems", "maxItems", "properties", "required", "minProperties", "maxProperties",
    "minLength", "maxLength", "pattern", "minimum", "maximum", "anyOf", "propertyOrdering",
    "additionalProperties", "defs", "ref", "$ref", "$defs",
    "min_items", "max_items", "min_properties", "max_properties", "min_length", "max_length",
    "any_of", "property_ordering", "additional_properties",
}

_KEYWORD_HINTS = {
    "$schema": "Remove it; generators such as zod-to-json-schema add it automatically.",
    "oneOf": "Use anyOf instead.",
    "const": "Use a single-value enum instead.",
    "examples": "Use 'example' (a single value) instead.",
    "exclusiveMinimum": "Use 'minimum' instead.",
    "exclusiveMaximum": "Use 'maximum' instead.",
}


def _uses_schema_object(tool: ToolDef) -> bool:
    return tool.schema_key not in ("parametersJsonSchema", "parameters_json_schema")


@rule("GM001", Severity.ERROR, "Function name starts with a letter/underscore; a-z A-Z 0-9 _ . : -; max 128",
      GEMINI_DECL, targets=_TARGET)
def gemini_name(tool: ToolDef) -> Iterable[Issue]:
    if isinstance(tool.name, str) and tool.name and not _NAME.match(tool.name):
        yield Issue(tool.location + "/name", f"function name '{tool.name}' is not valid for Gemini",
                    "Start with a letter or '_' and use only letters, digits, '_', '.', ':' or '-' (max 128).")


@rule("GM002", Severity.ERROR, "Parameter names start with a letter/underscore; a-z A-Z 0-9 _; max 64",
      GEMINI_DECL, targets=_TARGET)
def gemini_param_names(tool: ToolDef) -> Iterable[Issue]:
    props = tool.schema.get("properties") if isinstance(tool.schema, dict) else None
    if not isinstance(props, dict):
        return
    for name in props:
        if not _PARAM.match(name):
            yield Issue(tool.schema_location + "/properties",
                        f"parameter name '{name}' is not valid for Gemini",
                        "Start with a letter or '_' and use only letters, digits and '_' (max 64); "
                        "hyphens and dots are not allowed.")


@rule("GM003", Severity.ERROR, "Only keywords that exist on Gemini's Schema object", GEMINI_SCHEMA,
      targets=_TARGET)
def gemini_keywords(tool: ToolDef) -> Iterable[Issue]:
    if not _uses_schema_object(tool):
        return
    for node in walk(tool.schema):
        if not isinstance(node.schema, dict):
            continue
        for key in node.schema:
            if key not in SCHEMA_FIELDS:
                yield Issue(schema_path(tool, node.segments) + "/" + key.replace("~", "~0").replace("/", "~1"),
                            f"'{key}' is not a field of Gemini's Schema object",
                            _KEYWORD_HINTS.get(key, "Remove it or rewrite it with a supported keyword.")
                            + " Alternatively send this schema as 'parametersJsonSchema'.")


@rule("GM004", Severity.ERROR, "'type' is a single value, not an array", GEMINI_SCHEMA, targets=_TARGET)
def gemini_type_array(tool: ToolDef) -> Iterable[Issue]:
    if not _uses_schema_object(tool):
        return
    for node in walk(tool.schema):
        if isinstance(node.schema, dict) and isinstance(node.schema.get("type"), list):
            types = node.schema["type"]
            hint = ("Use the single type with \"nullable\": true." if "null" in types and len(types) == 2
                    else "Use anyOf with one schema per type.")
            yield Issue(schema_path(tool, node.segments) + "/type",
                        f"type {types!r} is an array; Gemini's Schema takes one type", hint)


@rule("GM005", Severity.ERROR, "'enum' values are strings", GEMINI_SCHEMA, targets=_TARGET)
def gemini_enum_strings(tool: ToolDef) -> Iterable[Issue]:
    if not _uses_schema_object(tool):
        return
    for node in walk(tool.schema):
        s = node.schema
        if isinstance(s, dict) and isinstance(s.get("enum"), list):
            bad = [v for v in s["enum"] if not isinstance(v, str)]
            if bad:
                yield Issue(schema_path(tool, node.segments) + "/enum",
                            f"enum contains non-string values {bad!r}; Gemini's Schema enum is a list of strings",
                            "Quote the values (e.g. [\"1\", \"2\"]) and keep the numeric 'type'.")
