"""Shared data types."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

DEFINITION_KINDS = ("function", "class", "method")
KINDS = DEFINITION_KINDS + ("import", "variable", "unreachable", "module")

# A removal starts out ticked in human review only if it was proven against the
# tests, the analyzer is reasonably sure about it, and AI raised no risk warning.
MIN_CONFIDENCE_TICKED = 50


@dataclass
class Removal:
    """One piece of dead code that could be deleted."""

    key: str                  # stable id, e.g. "inventory/pricing.py::calculate_tax_v1"
    kind: str                 # one of KINDS
    name: str                 # human-readable name shown in reports
    path: str                 # file path relative to the project root (POSIX style)
    start: int                # first line (1-based, inclusive)
    end: int                  # last line (1-based, inclusive)
    col: int = 0              # indentation of the first line
    confidence: int = 90      # 0-100: how sure the analyzer is
    reasons: list[str] = field(default_factory=list)
    # Keys of other removals that use this one. If any of them is kept, this one
    # must be kept too (otherwise kept code would call something deleted).
    used_by: list[str] = field(default_factory=list)
    import_info: dict | None = None   # for kind == "import": how to rewrite the statement
    status: str = "candidate"         # candidate | verified | unverified | needed
    status_reason: str = ""
    number: int = 0                   # position in the report, assigned per run
    ai_note: str | None = None
    risk: str | None = None           # AI risk warning, if any
    held_by: str | None = None        # starts kept because this other removal starts kept

    @property
    def lines(self) -> int:
        return self.end - self.start + 1

    @property
    def default_keep(self) -> bool:
        return (self.status != "verified" or self.confidence < MIN_CONFIDENCE_TICKED
                or bool(self.risk) or bool(self.held_by))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["lines"] = self.lines
        d["default_keep"] = self.default_keep
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Removal":
        fields = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**fields)


@dataclass
class TestOnly:
    """A definition or module used by tests and nothing else."""

    key: str
    kind: str
    name: str
    path: str
    start: int
    end: int
    used_in: list[str] = field(default_factory=list)  # test files that use it

    def to_dict(self) -> dict:
        return asdict(self)
