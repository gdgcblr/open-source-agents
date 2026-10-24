"""Benchmark dataset format (JSONL, one case per line).

Required: ``id``, ``prompt``. Optional:

* ``category``: expected task type (coding, research, extraction, writing, general)
* ``model``: model id for this case (defaults to the runner's ``--model``)
* ``tags``: e.g. ``["good-prompt"]`` marks prompts that should be left unchanged
* ``accept`` / ``answers``: simulate a user accepting patches or answering questions
* ``expect``: deterministic assertions on the toolkit's output
    - ``task_type``: str
    - ``rules``: rule ids that must fire
    - ``absent_rules``: rule ids that must not fire
    - ``changed``: bool
    - ``status``: str
    - ``preserved``: strings that must appear verbatim in the enhanced prompt
    - ``max_token_overhead``: int
* ``checks``: assertions on a *model's answer*, used only by the end-to-end runner (see e2e.py)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_EXPECT_KEYS = {"task_type", "rules", "absent_rules", "changed", "status", "preserved", "max_token_overhead"}


class DatasetError(ValueError):
    pass


@dataclass
class Case:
    id: str
    prompt: str
    category: str | None = None
    model: str | None = None
    tags: list[str] = field(default_factory=list)
    accept: list[str] = field(default_factory=list)
    answers: dict[str, str] = field(default_factory=dict)
    expect: dict[str, Any] = field(default_factory=dict)
    checks: list[dict[str, Any]] = field(default_factory=list)


def parse_case(obj: Any, where: str) -> Case:
    if not isinstance(obj, dict):
        raise DatasetError(f"{where}: each line must be a JSON object")
    for key in ("id", "prompt"):
        if not isinstance(obj.get(key), str) or not obj[key]:
            raise DatasetError(f"{where}: '{key}' is required and must be a non-empty string")
    expect = obj.get("expect", {})
    if not isinstance(expect, dict) or set(expect) - _EXPECT_KEYS:
        raise DatasetError(f"{where}: unknown 'expect' keys {sorted(set(expect) - _EXPECT_KEYS)}")
    checks = obj.get("checks", [])
    if not isinstance(checks, list) or not all(isinstance(c, dict) and "type" in c for c in checks):
        raise DatasetError(f"{where}: 'checks' must be a list of objects with a 'type'")
    return Case(
        id=obj["id"], prompt=obj["prompt"], category=obj.get("category"), model=obj.get("model"),
        tags=list(obj.get("tags", [])), accept=list(obj.get("accept", [])), answers=dict(obj.get("answers", {})),
        expect=expect, checks=checks,
    )


def load_cases(path: str | Path) -> list[Case]:
    p = Path(path)
    cases: list[Case] = []
    ids: set[str] = set()
    for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("//"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise DatasetError(f"{p.name}:{n}: invalid JSON: {e.msg}") from e
        case = parse_case(obj, f"{p.name}:{n}")
        if case.id in ids:
            raise DatasetError(f"{p.name}:{n}: duplicate id {case.id!r}")
        ids.add(case.id)
        cases.append(case)
    if not cases:
        raise DatasetError(f"{p.name}: no cases found")
    return cases
