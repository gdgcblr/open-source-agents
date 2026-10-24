"""tool-schema-lint: static checks for LLM tool / function definitions."""

__version__ = "0.1.0"

from .linter import LintResult, lint
from .loader import load_tools, read_json
from .models import Finding, InputError, Severity, ToolDef

__all__ = ["Finding", "InputError", "LintResult", "Severity", "ToolDef", "__version__", "lint", "load_tools",
           "read_json"]
