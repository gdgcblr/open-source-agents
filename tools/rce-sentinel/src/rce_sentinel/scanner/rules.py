"""Pluggable rule engine: AST matching for Python, lint-style regex for JS/TS and Go."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rce_sentinel.config import load_yaml
from rce_sentinel.models import Finding
from rce_sentinel.scanner.pyast import (
    ImportMap,
    enclosing_function,
    function_ranges,
    is_constant,
    module_name_for,
    normalized_source,
    stable_hash,
)

SUPPRESS_RE = re.compile(r"rce-sentinel:\s*ignore(?:\[([\w,\- ]+)\])?")


@dataclass
class Rule:
    id: str
    title: str
    cwe: str
    severity: str
    attacker_path: str
    fix: str
    match: list[str] = field(default_factory=list)
    method_names: list[str] = field(default_factory=list)
    arg: int = 0
    when_kwarg_true: str | None = None
    safe_kwarg: dict[str, list[str]] = field(default_factory=dict)
    pattern: re.Pattern[str] | None = None


@dataclass
class RulePack:
    language: str
    extensions: list[str]
    rules: list[Rule]
    sources: Any
    sanitizers: list[str] = field(default_factory=list)
    linter: str = "regex"


@dataclass
class RuleSet:
    packs: list[RulePack]
    version: str

    def pack_for(self, path: str) -> RulePack | None:
        suffix = Path(path).suffix.lower()
        return next((p for p in self.packs if suffix in p.extensions), None)

    @property
    def python(self) -> RulePack | None:
        return next((p for p in self.packs if p.language == "python"), None)


def load_rules(rule_files: list[Path], version: str) -> RuleSet:
    packs = []
    for path in rule_files:
        data = load_yaml(path)
        rules = []
        for r in data.get("rules", []):
            pattern = re.compile(r["pattern"]) if r.get("pattern") else None
            rules.append(
                Rule(
                    id=r["id"],
                    title=r["title"],
                    cwe=r["cwe"],
                    severity=r["severity"],
                    attacker_path=r.get("attacker_path", ""),
                    fix=r.get("fix", ""),
                    match=r.get("match", []),
                    method_names=r.get("method_names", []),
                    arg=r.get("arg", 0),
                    when_kwarg_true=r.get("when_kwarg_true"),
                    safe_kwarg=r.get("safe_kwarg", {}),
                    pattern=pattern,
                )
            )
        packs.append(
            RulePack(
                language=data["language"],
                extensions=data.get("extensions", []),
                rules=rules,
                sources=data.get("sources", {}),
                sanitizers=data.get("sanitizers", []),
                linter=data.get("linter", "regex"),
            )
        )
    return RuleSet(packs=packs, version=version)


def _suppressed(lines: list[str], line: int, rule_id: str) -> bool:
    for ln in (line - 1, line - 2):
        if 0 <= ln < len(lines) and (m := SUPPRESS_RE.search(lines[ln])):
            return m.group(1) is None or rule_id in [x.strip() for x in m.group(1).split(",")]
    return False


def _render_path(template: str, source: str | None, sink: str) -> str:
    src = source or "input to this call"
    return template.replace("{source}", src).replace("{sink}", sink)


# --- Python -----------------------------------------------------------------


@dataclass
class PyModule:
    path: str
    source: str
    tree: ast.Module
    imports: ImportMap
    ranges: list[tuple[int, int, ast.AST]]


def parse_python(path: str, source: str) -> PyModule | None:
    try:
        tree = ast.parse(source, filename=path)
    except (SyntaxError, ValueError):
        return None
    module = module_name_for(path)
    return PyModule(path, source, tree, ImportMap.build(tree, module), function_ranges(tree))


def rule_matches_call(rule: Rule, call: ast.Call, resolved: str | None) -> bool:
    by_name = bool(resolved) and resolved in rule.match
    by_method = isinstance(call.func, ast.Attribute) and call.func.attr in rule.method_names
    if not (by_name or by_method):
        return False
    kwargs = {k.arg: k.value for k in call.keywords if k.arg}
    if rule.when_kwarg_true:
        val = kwargs.get(rule.when_kwarg_true)
        if val is None or (isinstance(val, ast.Constant) and not val.value):
            return False
    for kw, safe_values in rule.safe_kwarg.items():
        val = kwargs.get(kw)
        if val is None and kw == "Loader" and len(call.args) > 1:
            val = call.args[1]
        if val is not None and ast.unparse(val) in safe_values:
            return False
    return True


def payload_arg(rule: Rule, call: ast.Call) -> ast.AST | None:
    if len(call.args) > rule.arg:
        return call.args[rule.arg]
    return call.keywords[0].value if call.keywords else None


def scan_python(mod: PyModule, pack: RulePack, allow_suppress: bool) -> list[Finding]:
    findings = []
    lines = mod.source.splitlines()
    for node in ast.walk(mod.tree):
        if not isinstance(node, ast.Call):
            continue
        resolved = mod.imports.resolve(node.func)
        for rule in pack.rules:
            if not rule_matches_call(rule, node, resolved):
                continue
            arg = payload_arg(rule, node)
            arg_kind = "constant" if arg is not None and is_constant(arg) else "unknown"
            encl = enclosing_function(mod.ranges, node.lineno)
            scope_src = normalized_source(encl[2]) if encl else ast.unparse(node)
            sink = resolved or ast.unparse(node.func)
            snippet = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
            findings.append(
                Finding(
                    id=stable_hash(mod.path, rule.id, str(node.lineno), snippet),
                    layer="rule",
                    rule_id=rule.id,
                    title=rule.title,
                    cwe=rule.cwe,
                    file=mod.path,
                    line=node.lineno,
                    snippet=snippet[:300],
                    sink=sink,
                    arg_kind=arg_kind,
                    attacker_path=_render_path(rule.attacker_path, None, sink),
                    fix=rule.fix,
                    context_hash=stable_hash(rule.id, scope_src),
                    scope=(encl[0], encl[1]) if encl else None,
                    suppressed=allow_suppress and _suppressed(lines, node.lineno, rule.id),
                )
            )
    return findings


# --- Regex (JS/TS, Go) -------------------------------------------------------


def strip_comments(src: str) -> str:
    """Blank out // and /* */ comments outside string literals, keeping line numbers."""
    out: list[str] = []
    i, n = 0, len(src)
    quote: str | None = None
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if quote:
            out.append(c)
            if c == "\\" and nxt:
                out.append(nxt)
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
        elif c in "'\"`":
            quote = c
            out.append(c)
            i += 1
        elif c == "/" and nxt == "/":
            while i < n and src[i] != "\n":
                out.append(" ")
                i += 1
        elif c == "/" and nxt == "*":
            end = src.find("*/", i + 2)
            end = n if end == -1 else end + 2
            out.extend("\n" if ch == "\n" else " " for ch in src[i:end])
            i = end
        else:
            out.append(c)
            i += 1
    return "".join(out)


def build_finding(path: str, raw_lines: list[str], rule: Rule, line: int, arg_kind: str,
                  source: str | None, scope: tuple[int, int] | None,
                  allow_suppress: bool) -> Finding:
    """Finding for a non-Python backend (regex, ESLint, gosec): same shape for all."""
    snippet = raw_lines[line - 1].strip() if 0 < line <= len(raw_lines) else ""
    if scope:
        body = "\n".join(raw_lines[scope[0] - 1 : scope[1]])
        context = " ".join(strip_comments(body).split())
    else:
        context = snippet
    return Finding(
        id=stable_hash(path, rule.id, str(line), snippet),
        layer="taint" if arg_kind == "tainted" else "rule",
        rule_id=rule.id,
        title=rule.title,
        cwe=rule.cwe,
        file=path,
        line=line,
        snippet=snippet[:300],
        sink=rule.id,
        source=source,
        taint_chain=[source] if source else [],
        arg_kind=arg_kind,  # type: ignore[arg-type]
        attacker_path=_render_path(rule.attacker_path, source, rule.id),
        fix=rule.fix,
        context_hash=stable_hash(rule.id, context, source or ""),
        scope=scope,
        suppressed=allow_suppress and _suppressed(raw_lines, line, rule.id),
    )


ASSIGN_RE = re.compile(r"\b(?:const|let|var)?\s*([A-Za-z_$][\w$]*)\s*:?=\s*(.+)")


def scan_regex(path: str, source: str, pack: RulePack, allow_suppress: bool) -> list[Finding]:
    raw_lines = source.splitlines()
    code_lines = strip_comments(source).splitlines()
    src_res = [re.compile(s) for s in pack.sources]
    tainted: dict[str, str] = {}
    findings = []
    for idx, line in enumerate(code_lines, start=1):
        if (m := ASSIGN_RE.search(line)) and (
            any(r.search(m.group(2)) for r in src_res)
            or any(re.search(rf"\b{re.escape(t)}\b", m.group(2)) for t in tainted)
        ):
            tainted[m.group(1)] = m.group(2).strip().rstrip(";")[:80]
        for rule in pack.rules:
            if not rule.pattern or not rule.pattern.search(line):
                continue
            source_hit = next((m.group(0) for r in src_res if (m := r.search(line))), None)
            name_hit = next((t for t in tainted if re.search(rf"\b{re.escape(t)}\b", line)), None)
            arg_kind = "tainted" if (source_hit or name_hit) else "unknown"
            src_desc = name_hit and f"`{name_hit}` (from {tainted[name_hit]})"
            src_desc = src_desc or (source_hit and f"`{source_hit}`")
            findings.append(build_finding(path, raw_lines, rule, idx, arg_kind,
                                          src_desc or None, None, allow_suppress))
    return findings
