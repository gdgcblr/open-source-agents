"""Reachability: does the repo actually call the vulnerable symbol of a dependency?

Python only. Calls are resolved through import aliases and compared to the advisory's
affected symbols (OSV data or the curated overlay in config/symbols.yaml). A call that a
rule marks safe, such as `yaml.load(x, Loader=SafeLoader)`, does not count as reachable.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from rce_sentinel.models import Advisory, Dependency
from rce_sentinel.scanner.rules import PyModule, RulePack, rule_matches_call


@dataclass
class Reach:
    reachable: bool | None
    evidence: list[str]
    imported: bool


def import_names(dep: Dependency, overlay: dict[str, list[str]]) -> list[str]:
    return overlay.get(dep.name, [dep.name.replace("-", "_")])


def _symbol_hit(resolved: str, symbols: list[str]) -> bool:
    return any(resolved == s or resolved.startswith(s + ".") for s in symbols)


def check(adv: Advisory, dep: Dependency, modules: list[PyModule],
          overlay: dict[str, list[str]], pack: RulePack | None) -> Reach:
    if dep.ecosystem != "PyPI":
        return Reach(None, ["reachability is implemented for Python only"], False)
    roots = import_names(dep, overlay)
    imported = any(
        m == r or m.startswith(r + ".")
        for mod in modules for m in mod.imports.imported_modules for r in roots
    )
    if not adv.symbols:
        why = "imported; advisory lists no symbols" if imported else "never imported"
        return Reach(None if imported else False, [why], imported)
    evidence: list[str] = []
    safe_uses: list[str] = []
    for mod in modules:
        for node in ast.walk(mod.tree):
            if not isinstance(node, ast.Call):
                continue
            resolved = mod.imports.resolve(node.func) or ""
            if not _symbol_hit(resolved, adv.symbols):
                continue
            loc = f"{mod.path}:{node.lineno} {resolved}"
            gating = [r for r in (pack.rules if pack else []) if resolved in r.match]
            if gating and not any(rule_matches_call(r, node, resolved) for r in gating):
                safe_uses.append(f"{loc} (safe arguments)")
            else:
                evidence.append(loc)
    if evidence:
        return Reach(True, evidence[:5], True)
    why = safe_uses[:3] or [f"no call to {', '.join(adv.symbols[:3])}"]
    return Reach(False, why, imported)
