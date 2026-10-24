"""Check registry. A check is a function decorated with @check that returns findings.

Adding a check means writing one function in prcheck/checks/ - the runner, CLI,
JSON report and `prcheck rules` pick it up automatically.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .context import ProjectContext
from .models import Finding, Severity

CheckFunc = Callable[[ProjectContext], Iterable[Finding]]


@dataclass(frozen=True)
class CheckSpec:
    id: str
    group: str
    title: str
    severity: Severity  # default severity of this check's findings
    rule: str  # where the rule comes from, shown by `prcheck rules`
    func: CheckFunc


_REGISTRY: dict[str, CheckSpec] = {}


def check(id: str, *, group: str, title: str, severity: Severity, rule: str) -> Callable[[CheckFunc], CheckFunc]:
    def decorator(func: CheckFunc) -> CheckFunc:
        if id in _REGISTRY:
            raise ValueError(f"Duplicate check id {id}")
        _REGISTRY[id] = CheckSpec(id=id, group=group, title=title, severity=severity, rule=rule, func=func)
        return func

    return decorator


def all_checks() -> list[CheckSpec]:
    from . import checks  # noqa: F401  (importing registers every check)

    return list(_REGISTRY.values())


def finding(spec_id: str, message: str, *, file: str | None = None, line: int | None = None,
            severity: Severity | None = None) -> Finding:
    """Build a finding, defaulting to the registered severity of check `spec_id`."""
    default = _REGISTRY[spec_id].severity if spec_id in _REGISTRY else Severity.ERROR
    return Finding(message=message, severity=severity or default, file=file, line=line)
