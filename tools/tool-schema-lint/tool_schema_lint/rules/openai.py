"""OpenAI function-calling and Structured Outputs (strict mode) rules.

Strict-mode rules (S0xx) target "openai-strict". When the target is plain "openai", the
engine also enables them for each tool that declares `strict: true`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from ..models import FORMAT_OPENAI, TARGET_OPENAI_STRICT, Severity, ToolDef
from ..schema_walk import walk
from . import Issue, rule, set_rule
from .general import object_nodes, schema_path

OPENAI_FC = "OpenAI docs, Function calling guide"
OPENAI_NAME = "OpenAI API request validation for function names (400 error: ^[a-zA-Z0-9_-]{1,64}$)"
OPENAI_SO = "OpenAI docs, Structured Outputs 'Supported schemas'"

_ANY_OPENAI = [FORMAT_OPENAI, TARGET_OPENAI_STRICT]
_STRICT = [TARGET_OPENAI_STRICT]

_NAME = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
MAX_TOOLS_SOFT = 20
UNSUPPORTED_KEYWORDS = ("allOf", "not", "dependentRequired", "dependentSchemas", "if", "then", "else")
SUPPORTED_FORMATS = {"date-time", "time", "date", "duration", "email", "hostname", "ipv4", "ipv6", "uuid"}
MAX_NESTING = 10
MAX_PROPERTIES = 5000
MAX_ENUM_VALUES = 1000
MAX_STRING_CHARS = 120_000
LARGE_ENUM = 250
LARGE_ENUM_CHARS = 15_000


@rule("O001", Severity.ERROR, "Function name matches ^[a-zA-Z0-9_-]{1,64}$", OPENAI_NAME, targets=_ANY_OPENAI)
def openai_name(tool: ToolDef) -> Iterable[Issue]:
    if isinstance(tool.name, str) and tool.name and not _NAME.match(tool.name):
        reason = ("is longer than 64 characters" if len(tool.name) > 64
                  else "contains characters other than a-z A-Z 0-9 _ -")
        yield Issue(tool.location + "/name", f"function name '{tool.name}' {reason}",
                    "OpenAI rejects the request with a 400 error. Replace '.', ':' and spaces with '_'.")


@set_rule("O002", Severity.INFO, f"Fewer than {MAX_TOOLS_SOFT} tools are offered at once", OPENAI_FC,
          targets=_ANY_OPENAI)
def openai_tool_count(tools: list[ToolDef]) -> Iterable[Issue]:
    if len(tools) >= MAX_TOOLS_SOFT:
        yield Issue("", f"{len(tools)} tools defined; OpenAI suggests fewer than {MAX_TOOLS_SOFT} per turn",
                    "Split the tools by task or load them on demand to improve tool selection.")


@rule("S001", Severity.ERROR, "Every object sets additionalProperties: false", OPENAI_SO, targets=_STRICT)
def strict_additional_properties(tool: ToolDef) -> Iterable[Issue]:
    for node in object_nodes(tool):
        if node.schema.get("additionalProperties") is not False:
            yield Issue(schema_path(tool, node.segments),
                        "object does not set \"additionalProperties\": false (required in strict mode)",
                        "Add \"additionalProperties\": false to this object.")


@rule("S002", Severity.ERROR, "Every property is listed in 'required'", OPENAI_SO, targets=_STRICT)
def strict_all_required(tool: ToolDef) -> Iterable[Issue]:
    for node in object_nodes(tool):
        props = node.schema.get("properties")
        if not isinstance(props, dict):
            continue
        req = node.schema.get("required")
        req = set(req) if isinstance(req, list) else set()
        missing = [p for p in props if p not in req]
        if missing:
            yield Issue(schema_path(tool, node.segments) + "/required",
                        "strict mode requires every property in 'required'; missing: " + ", ".join(missing),
                        "Make optional fields required but nullable: \"anyOf\": [{\"type\": \"string\"}, "
                        "{\"type\": \"null\"}] works for OpenAI and Gemini; \"type\": [\"string\", \"null\"] "
                        "works for OpenAI only.")


@rule("S003", Severity.ERROR, "Root schema does not use anyOf", OPENAI_SO, targets=_STRICT)
def strict_root_anyof(tool: ToolDef) -> Iterable[Issue]:
    if isinstance(tool.schema, dict) and "anyOf" in tool.schema:
        yield Issue(tool.schema_location + "/anyOf", "root schema uses anyOf, which strict mode does not allow",
                    "Wrap the alternatives in a property of a root object.")


@rule("S004", Severity.ERROR, "No unsupported composition keywords", OPENAI_SO, targets=_STRICT)
def strict_keywords(tool: ToolDef) -> Iterable[Issue]:
    for node in walk(tool.schema):
        if not isinstance(node.schema, dict):
            continue
        for key in UNSUPPORTED_KEYWORDS:
            if key in node.schema:
                yield Issue(schema_path(tool, node.segments) + "/" + key,
                            f"'{key}' is not supported in strict mode",
                            "Rewrite with anyOf, or move the constraint into the description.")


@rule("S005", Severity.WARNING, "String formats are in the supported list", OPENAI_SO, targets=_STRICT)
def strict_formats(tool: ToolDef) -> Iterable[Issue]:
    for node in walk(tool.schema):
        s = node.schema
        if isinstance(s, dict) and isinstance(s.get("format"), str) and s.get("type") == "string" \
                and s["format"] not in SUPPORTED_FORMATS:
            yield Issue(schema_path(tool, node.segments) + "/format",
                        f"format '{s['format']}' is not in the strict-mode supported list",
                        "Supported: " + ", ".join(sorted(SUPPORTED_FORMATS)) + ". Use 'pattern' instead.")


@rule("S006", Severity.ERROR, "Schema stays within strict-mode size limits", OPENAI_SO, targets=_STRICT)
def strict_limits(tool: ToolDef) -> Iterable[Issue]:
    if not isinstance(tool.schema, dict):
        return
    levels = properties = enum_values = chars = 0
    for node in walk(tool.schema):
        s = node.schema
        if not isinstance(s, dict):
            continue
        for key in ("$defs", "definitions"):
            if isinstance(s.get(key), dict):
                chars += sum(len(k) for k in s[key])
        if isinstance(s.get("properties"), dict):
            levels = max(levels, node.depth + 1)
            properties += len(s["properties"])
            chars += sum(len(k) for k in s["properties"])
        if "const" in s:
            chars += len(str(s["const"]))
        if isinstance(s.get("enum"), list):
            values = s["enum"]
            enum_values += len(values)
            enum_chars = sum(len(str(v)) for v in values)
            chars += enum_chars
            if len(values) > LARGE_ENUM and enum_chars > LARGE_ENUM_CHARS:
                yield Issue(schema_path(tool, node.segments) + "/enum",
                            f"enum has {len(values)} values totalling {enum_chars} characters "
                            f"(limit {LARGE_ENUM_CHARS} when there are more than {LARGE_ENUM} values)")
    here = tool.schema_location
    if levels > MAX_NESTING:
        yield Issue(here, f"objects are nested {levels} levels deep (limit {MAX_NESTING})")
    if properties > MAX_PROPERTIES:
        yield Issue(here, f"{properties} object properties in total (limit {MAX_PROPERTIES})")
    if enum_values > MAX_ENUM_VALUES:
        yield Issue(here, f"{enum_values} enum values in total (limit {MAX_ENUM_VALUES})")
    if chars > MAX_STRING_CHARS:
        yield Issue(here, f"{chars} characters of property names, definition names, enum and const values "
                          f"(limit {MAX_STRING_CHARS})")
