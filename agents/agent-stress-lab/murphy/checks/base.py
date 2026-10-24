"""Check contract: a check looks at one finished run and says pass or fail."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from murphy.config.schema import PersonaConfig


@dataclass
class RunContext:
    run_dir: Path
    persona: PersonaConfig
    trace: list[dict]
    end_reason: str
    vars: dict[str, Any] = field(default_factory=dict)

    @property
    def tool_events(self) -> list[dict]:
        return [e for e in self.trace if e["kind"] == "tool"]

    def substitute(self, text: str) -> str:
        """Replace ${vars.name} and ${persona.id} placeholders."""
        def sub(m: re.Match) -> str:
            scope, name = m.group(1), m.group(2)
            if scope == "persona":
                return str(getattr(self.persona, name))
            return str(self.vars.get(name, ""))
        return re.sub(r"\$\{(vars|persona)\.([A-Za-z0-9_]+)\}", sub, text)


@dataclass
class CheckResult:
    id: str
    passed: bool
    label: str
    message: str = ""
    hint: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class Check(Protocol):
    id: str
    label: str
    hint: str

    def run(self, ctx: RunContext) -> CheckResult: ...
