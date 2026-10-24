from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass, field
from pathlib import Path

from commute_gate.config import ROOT
from commute_gate.policy.base import EvalCheck, GateCheck
from commute_gate.policy.evals import BUILTIN_EVALS
from commute_gate.policy.gates import BUILTIN_GATES

DEFAULT_GATES = ("required_slots", "known_places", "vague_place", "accessibility")
DEFAULT_EVALS = (
    "tool_available",
    "tool_faithfulness",
    "memory_consistency",
    "goal_alignment",
)


@dataclass
class PolicySpec:
    gates: list[str] = field(default_factory=lambda: list(DEFAULT_GATES))
    evals: list[str] = field(default_factory=lambda: list(DEFAULT_EVALS))
    extension_dirs: list[str] = field(default_factory=list)
    source: str = "defaults"


def parse_simple_yaml(text: str) -> dict[str, list[str]]:
    """Tiny YAML-subset loader for list-of-strings maps. No PyYAML required."""
    data: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.endswith(":") and not line.strip().startswith("-"):
            current = line.strip()[:-1]
            data.setdefault(current, [])
            continue
        if current and line.strip().startswith("-"):
            data[current].append(line.strip()[1:].strip().strip("'\""))
    return data


def load_policy_spec(path: Path | None = None) -> PolicySpec:
    env_gates = os.getenv("POLICY_GATES", "").strip()
    env_evals = os.getenv("POLICY_EVALS", "").strip()
    file_path = path or Path(os.getenv("POLICY_FILE", str(ROOT / "policy.yaml")))
    spec = PolicySpec()
    if file_path.exists():
        parsed = parse_simple_yaml(file_path.read_text(encoding="utf-8"))
        if parsed.get("gates"):
            spec.gates = parsed["gates"]
        if parsed.get("evals"):
            spec.evals = parsed["evals"]
        if parsed.get("extensions"):
            spec.extension_dirs = parsed["extensions"]
        spec.source = str(file_path)
    if env_gates:
        spec.gates = [item.strip() for item in env_gates.split(",") if item.strip()]
        spec.source = f"{spec.source}+POLICY_GATES"
    if env_evals:
        spec.evals = [item.strip() for item in env_evals.split(",") if item.strip()]
        spec.source = f"{spec.source}+POLICY_EVALS"
    extra = os.getenv("POLICY_EXTENSIONS", "").strip()
    if extra:
        spec.extension_dirs.extend(item.strip() for item in extra.split(",") if item.strip())
    return spec


def _load_extension_dir(directory: Path, gates: dict[str, GateCheck], evals: dict[str, EvalCheck]) -> None:
    if not directory.is_dir():
        return
    for file in sorted(directory.glob("*.py")):
        if file.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"commute_ext_{file.stem}", file)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for value in vars(module).values():
            kind = getattr(value, "kind", None)
            if kind not in {"gate", "eval"}:
                continue
            check = value() if isinstance(value, type) else value
            if not hasattr(check, "name") or not hasattr(check, "run"):
                continue
            if kind == "eval":
                evals[check.name] = check
            else:
                gates[check.name] = check


def resolve_policy(spec: PolicySpec | None = None) -> tuple[list[GateCheck], list[EvalCheck], PolicySpec]:
    spec = spec or load_policy_spec()
    gates = dict(BUILTIN_GATES)
    evals = dict(BUILTIN_EVALS)
    for raw_dir in spec.extension_dirs:
        directory = Path(raw_dir)
        if not directory.is_absolute():
            directory = ROOT / directory
        _load_extension_dir(directory, gates, evals)

    missing_gates = [name for name in spec.gates if name not in gates]
    missing_evals = [name for name in spec.evals if name not in evals]
    if missing_gates or missing_evals:
        raise ValueError(
            "Unknown policy checks: "
            + ", ".join([*(f"gate:{n}" for n in missing_gates), *(f"eval:{n}" for n in missing_evals)])
            + f". Available gates: {sorted(gates)}; evals: {sorted(evals)}"
        )
    return [gates[name] for name in spec.gates], [evals[name] for name in spec.evals], spec
