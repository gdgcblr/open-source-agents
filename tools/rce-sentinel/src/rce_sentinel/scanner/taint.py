"""Source-to-sink taint tracing for Python, within and across the scanned files.

Per function, names assigned from untrusted sources (request params, argv, env, file reads)
are tracked through assignments, string building, and calls. Function summaries record which
parameters reach a sink and whether the return value is tainted, so a tainted argument in
`views.py` that reaches `os.system` inside `utils.run()` is reported with the full chain.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from rce_sentinel.models import Finding
from rce_sentinel.scanner.pyast import name_matches, stable_hash
from rce_sentinel.scanner.rules import (
    PyModule,
    RulePack,
    _render_path,
    payload_arg,
    rule_matches_call,
)

Chain = list[str]
PARAM = "param:"


@dataclass
class Summary:
    param_sinks: dict[int, list[tuple[str, int, str]]] = field(default_factory=dict)
    returns: Chain | None = None


@dataclass
class TaintContext:
    pack: RulePack
    summaries: dict[str, Summary]
    module: PyModule

    def is_source(self, resolved: str | None, is_call: bool) -> bool:
        if not resolved:
            return False
        src = self.pack.sources
        names = list(src.get("attributes", []))
        if is_call:
            names += src.get("calls", []) + src.get("file_reads", [])
        for s in names:
            if name_matches(resolved, s) or resolved.startswith(s + "."):
                return True
        if not is_call:
            return False
        return any(resolved.startswith(f + ".") for f in src.get("file_reads", []))

    def is_sanitizer(self, resolved: str | None) -> bool:
        return bool(resolved) and any(name_matches(resolved, s) for s in self.pack.sanitizers)


class FunctionTaint(ast.NodeVisitor):
    """Single forward pass over a function body in source order."""

    def __init__(self, ctx: TaintContext, func: ast.AST | None, qualname: str):
        self.ctx = ctx
        self.qualname = qualname
        self.tainted: dict[str, Chain] = {}
        self.sink_hits: list[tuple[ast.Call, Chain]] = []
        self.returns: Chain | None = None
        self.params: list[str] = []
        if isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef):
            self.params = [a.arg for a in func.args.args if a.arg not in {"self", "cls"}]
            route = self._is_route(func)
            for p in self.params:
                origin = f"route parameter `{p}`" if route else f"{PARAM}{p}"
                self.tainted[p] = [origin]

    def _is_route(self, func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        names = self.ctx.pack.sources.get("route_decorators", [])
        for dec in func.decorator_list:
            target = dec.func if isinstance(dec, ast.Call) else dec
            resolved = self.ctx.module.imports.resolve(target) or ""
            if resolved.split(".")[-1] in names:
                return True
        return False

    def loc(self, node: ast.AST) -> str:
        return f"{self.ctx.module.path}:{getattr(node, 'lineno', 0)}"

    def taint_of(self, node: ast.AST | None) -> Chain | None:
        if node is None:
            return None
        imports = self.ctx.module.imports
        if isinstance(node, ast.Name):
            return self.tainted.get(node.id)
        if isinstance(node, ast.Attribute | ast.Subscript):
            if self.ctx.is_source(imports.resolve(node), is_call=False):
                return [f"`{ast.unparse(node)[:80]}` ({self.loc(node)})"]
            inner = node.value
            return self.taint_of(inner) or (
                self.taint_of(node.slice) if isinstance(node, ast.Subscript) else None
            )
        if isinstance(node, ast.Call):
            resolved = imports.resolve(node.func)
            if self.ctx.is_source(resolved, is_call=True):
                return [f"`{ast.unparse(node)[:80]}` ({self.loc(node)})"]
            if self.ctx.is_sanitizer(resolved):
                return None
            summary = self.ctx.summaries.get(resolved or "")
            if summary and summary.returns:
                return [*summary.returns, f"returned by `{resolved}`"]
            if isinstance(node.func, ast.Attribute) and (t := self.taint_of(node.func.value)):
                return t
            for a in [*node.args, *(k.value for k in node.keywords)]:
                if t := self.taint_of(a):
                    return t
            return None
        if isinstance(node, ast.JoinedStr):
            for v in node.values:
                if isinstance(v, ast.FormattedValue) and (t := self.taint_of(v.value)):
                    return t
            return None
        for child in ast.iter_child_nodes(node):
            if t := self.taint_of(child):
                return t
        return None

    def _bind(self, target: ast.AST, chain: Chain | None) -> None:
        if isinstance(target, ast.Name):
            if chain:
                self.tainted[target.id] = [*chain, f"`{target.id}` ({self.loc(target)})"]
            else:
                self.tainted.pop(target.id, None)
        elif isinstance(target, ast.Tuple | ast.List):
            for elt in target.elts:
                self._bind(elt, chain)

    def visit_Assign(self, node: ast.Assign) -> None:
        self.generic_visit(node)
        chain = self.taint_of(node.value)
        for t in node.targets:
            self._bind(t, chain)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.generic_visit(node)
        if node.value is not None:
            self._bind(node.target, self.taint_of(node.value))

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.generic_visit(node)
        if (chain := self.taint_of(node.value)) and isinstance(node.target, ast.Name):
            self._bind(node.target, chain)

    def visit_For(self, node: ast.For) -> None:
        self._bind(node.target, self.taint_of(node.iter))
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            if item.optional_vars is not None:
                self._bind(item.optional_vars, self.taint_of(item.context_expr))
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        self.generic_visit(node)
        chain = self.taint_of(node.value)
        if chain and not chain[0].startswith(PARAM):
            self.returns = chain

    def visit_Call(self, node: ast.Call) -> None:
        self.generic_visit(node)
        imports = self.ctx.module.imports
        resolved = imports.resolve(node.func)
        for rule in self.ctx.pack.rules:
            if rule_matches_call(rule, node, resolved):
                chain = self.taint_of(payload_arg(rule, node))
                if chain:
                    self.sink_hits.append((node, [*chain, f"sink `{resolved}`"]))
        summary = self.ctx.summaries.get(resolved or "")
        if summary:
            for idx, a in enumerate(node.args):
                chain = self.taint_of(a)
                if chain and idx in summary.param_sinks:
                    self.sink_hits.append((node, [*chain, f"call `{resolved}`"]))

    # Nested defs are analysed separately.
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def run(self, body: list[ast.stmt]) -> None:
        for stmt in body:
            self.visit(stmt)


def _functions(mod: PyModule) -> list[tuple[str, ast.AST | None, list[ast.stmt]]]:
    out: list[tuple[str, ast.AST | None, list[ast.stmt]]] = [
        (f"{mod.imports.module}.<module>", None, mod.tree.body)
    ]
    for node in ast.walk(mod.tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            out.append((f"{mod.imports.module}.{node.name}", node, node.body))
    return out


def trace(modules: list[PyModule], pack: RulePack) -> dict[tuple[str, int], Chain]:
    """Return {(file, line): chain} for sink call sites reached by untrusted data."""
    summaries: dict[str, Summary] = {}
    hits: dict[tuple[str, int], Chain] = {}
    for _ in range(3):  # fixpoint over cross-file summaries
        changed = False
        for mod in modules:
            ctx = TaintContext(pack, summaries, mod)
            for qualname, func, body in _functions(mod):
                ft = FunctionTaint(ctx, func, qualname)
                ft.run(body)
                summary = summaries.setdefault(qualname, Summary())
                if ft.returns and summary.returns is None:
                    summary.returns, changed = ft.returns, True
                for call, chain in ft.sink_hits:
                    origin = chain[0]
                    if origin.startswith(PARAM):
                        pname = origin.removeprefix(PARAM)
                        if pname in ft.params:
                            idx = ft.params.index(pname)
                            entry = (mod.path, call.lineno, chain[-1])
                            sinks = summary.param_sinks.setdefault(idx, [])
                            if entry not in sinks:
                                sinks.append(entry)
                                changed = True
                    else:
                        key = (mod.path, call.lineno)
                        before = len(hits)
                        hits.setdefault(key, chain)
                        _propagate_to_callee(summaries, call, mod, chain, hits)
                        changed = changed or len(hits) > before
        if not changed:
            break
    return hits


def _propagate_to_callee(
    summaries: dict[str, Summary],
    call: ast.Call,
    mod: PyModule,
    chain: Chain,
    hits: dict[tuple[str, int], Chain],
) -> None:
    """Mark the sink inside the callee as tainted too, with the caller's chain."""
    resolved = mod.imports.resolve(call.func) or ""
    summary = summaries.get(resolved)
    if not summary:
        return
    for sinks in summary.param_sinks.values():
        for path, line, sink_desc in sinks:
            hits.setdefault((path, line), [*chain, f"into `{resolved}`", sink_desc])


def apply_taint(
    findings: list[Finding], hits: dict[tuple[str, int], Chain], pack: RulePack
) -> list[Finding]:
    """Upgrade rule findings whose sink is reached by tainted data."""
    templates = {r.id: r.attacker_path for r in pack.rules}
    for f in findings:
        chain = hits.get((f.file, f.line))
        if not chain:
            continue
        f.layer = "taint"
        f.arg_kind = "tainted"
        f.taint_chain = chain
        f.source = chain[0]
        f.attacker_path = _render_path(templates.get(f.rule_id, ""), chain[0], f.sink)
        f.context_hash = stable_hash(f.context_hash, *chain)
    return findings
