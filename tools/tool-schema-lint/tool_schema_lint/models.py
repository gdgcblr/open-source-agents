"""Core data types shared by the loader, rules, and reporters."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class Severity(IntEnum):
    """Finding severity. Ordered so that comparisons work (ERROR > WARNING)."""

    INFO = 1
    WARNING = 2
    ERROR = 3

    def __str__(self) -> str:
        return self.name.lower()


# Source formats the loader understands.
FORMAT_MCP = "mcp"
FORMAT_OPENAI = "openai"
FORMAT_GEMINI = "gemini"
FORMAT_ANTHROPIC = "anthropic"
SOURCE_FORMATS = (FORMAT_MCP, FORMAT_OPENAI, FORMAT_GEMINI, FORMAT_ANTHROPIC)

# Lint targets. "openai-strict" applies OpenAI Structured Outputs rules to every tool,
# while "openai" applies them only to tools that declare `strict: true`.
TARGET_OPENAI_STRICT = "openai-strict"
TARGETS = (FORMAT_MCP, FORMAT_OPENAI, TARGET_OPENAI_STRICT, FORMAT_GEMINI, FORMAT_ANTHROPIC)


@dataclass
class ToolDef:
    """A single tool definition, normalized from any supported provider format."""

    name: Any  # raw value; rules validate that it is a non-empty string
    description: Any
    schema: Any  # the parameters / inputSchema / input_schema object (may be None)
    source_format: str
    location: str  # JSON pointer of the tool inside the input document, e.g. "/tools/0"
    schema_location: str  # JSON pointer of the schema inside the input document
    schema_key: str  # key the schema was read from, e.g. "inputSchema"
    strict: bool = False
    raw: dict[str, Any] = field(default_factory=dict)
    # JSON pointer of the object holding name/description; differs from `location` for
    # OpenAI Chat Completions tools, where they live under "function".
    body_location: str = ""

    @property
    def label(self) -> str:
        return self.name if isinstance(self.name, str) and self.name else f"<unnamed {self.location}>"


@dataclass(frozen=True)
class Finding:
    """One problem reported by a rule."""

    rule_id: str
    severity: Severity
    tool: str
    path: str  # JSON pointer inside the input document
    message: str
    hint: str = ""
    file: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule_id,
            "severity": str(self.severity),
            "tool": self.tool,
            "path": self.path,
            "message": self.message,
            "hint": self.hint,
            "file": self.file,
        }


class InputError(Exception):
    """Raised when the input cannot be read or recognized. Maps to exit code 2."""
