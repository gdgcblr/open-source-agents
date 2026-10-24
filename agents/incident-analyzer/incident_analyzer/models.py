"""Pydantic models for the Incident Analyzer agent."""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class SymbolType(str, Enum):
    """Type of code symbol extracted from AST."""
    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    MODULE = "module"


class Severity(str, Enum):
    """Severity level of the diagnosed incident."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class CodeSymbol(BaseModel):
    """Represents a single code symbol (function, class, method) extracted via AST."""
    name: str = Field(description="Symbol name")
    symbol_type: SymbolType = Field(description="Type of symbol")
    file_path: str = Field(description="Relative file path")
    line_start: int = Field(description="Starting line number")
    line_end: int = Field(description="Ending line number")
    signature: str = Field(description="Function/method signature string")
    docstring: Optional[str] = Field(default=None, description="Docstring if present")
    decorators: list[str] = Field(default_factory=list, description="List of decorator names")
    calls: list[str] = Field(default_factory=list, description="List of function/method names called within this symbol")
    source_snippet: str = Field(default="", description="First 10 lines of source for context")


class ModuleSpec(BaseModel):
    """AST specification for a single Python module/file."""
    file_path: str = Field(description="Relative path of the module")
    imports: list[str] = Field(default_factory=list, description="Import statements")
    symbols: list[CodeSymbol] = Field(default_factory=list, description="Symbols defined in this module")
    module_docstring: Optional[str] = Field(default=None, description="Module-level docstring")


class CodebaseSpec(BaseModel):
    """Complete AST specification of the target codebase (generated during one-time setup)."""
    root_path: str = Field(description="Absolute root path of the indexed codebase")
    modules: list[ModuleSpec] = Field(default_factory=list, description="All indexed modules")
    total_symbols: int = Field(default=0, description="Total number of symbols indexed")
    total_files: int = Field(default=0, description="Total number of files indexed")

    def find_symbol(self, name: str) -> list[CodeSymbol]:
        """Find all symbols matching the given name across the codebase."""
        results = []
        for module in self.modules:
            for symbol in module.symbols:
                if symbol.name == name:
                    results.append(symbol)
        return results

    def find_symbols_in_file(self, file_path: str) -> list[CodeSymbol]:
        """Find all symbols in a specific file."""
        for module in self.modules:
            if module.file_path == file_path or module.file_path.endswith(file_path):
                return module.symbols
        return []


class IncidentInput(BaseModel):
    """Input data for incident analysis."""
    log_text: str = Field(description="Raw log output or stack trace")
    actual_output: Optional[str] = Field(default=None, description="Actual output observed")
    expected_output: Optional[str] = Field(default=None, description="Expected output")
    context: Optional[str] = Field(default=None, description="Additional context from the developer")


class AffectedSymbol(BaseModel):
    """A code symbol identified as related to the incident."""
    name: str = Field(description="Symbol name")
    file_path: str = Field(description="File containing the symbol")
    line_start: int = Field(description="Starting line")
    line_end: int = Field(description="Ending line")
    relevance: str = Field(description="Why this symbol is relevant to the incident")


class SuggestedFix(BaseModel):
    """A suggested code fix for the incident."""
    file_path: str = Field(description="File to be modified")
    original_code: str = Field(description="Original code snippet")
    fixed_code: str = Field(description="Suggested fixed code")
    explanation: str = Field(description="Why this fix resolves the issue")
    diff: Optional[str] = Field(default=None, description="Unified diff representation of the patch")
    patch_verified: Optional[bool] = Field(default=None, description="Whether the patch was verified via AST or git apply check")


class Diagnosis(BaseModel):
    """Structured diagnosis output from the incident analyzer."""
    root_cause: str = Field(description="Root cause analysis of the incident")
    severity: Severity = Field(description="Assessed severity level")
    affected_symbols: list[AffectedSymbol] = Field(default_factory=list, description="Code symbols involved")
    suggested_fixes: list[SuggestedFix] = Field(default_factory=list, description="Suggested code fixes")
    prevention_tips: list[str] = Field(default_factory=list, description="Tips to prevent recurrence")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score of the diagnosis")
