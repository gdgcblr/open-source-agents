"""Static analysis: find dead code by reading a Python project.

Five kinds of dead code are found: unused definitions (functions, classes,
methods), unused imports, unused local variables, unused modules, and
unreachable code. Definitions and modules used only by tests are reported
separately as test-only code.

The analyzer is conservative. Anything that could plausibly be used in a way
reading the code can't show (a decorator that registers it, an external base
class whose hook it may override, its name inside a string or a config file)
is protected and never reported. Removals are found as a fixpoint: code used
only by other dead code is dead too.
"""
from __future__ import annotations

import ast
import fnmatch
import re
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

from .model import DEFINITION_KINDS, Removal, TestOnly

EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules", "__pycache__",
    ".tox", ".nox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "build", "dist",
    "site-packages", ".eggs", ".idea", ".vscode", "reaper-out",
}

SAFE_DECORATORS = {
    "property", "staticmethod", "classmethod", "cached_property",
    "functools.cached_property", "lru_cache", "functools.lru_cache", "cache",
    "functools.cache", "wraps", "functools.wraps", "dataclass",
    "dataclasses.dataclass", "total_ordering", "functools.total_ordering",
}

DYNAMIC_CALLS = {"getattr", "hasattr", "globals", "locals", "vars", "__import__",
                 "eval", "exec", "import_module", "getmembers"}

CONFIG_SUFFIXES = {".toml", ".cfg", ".ini", ".yaml", ".yml", ".json", ".sh", ".bash",
                   ".ps1", ".bat", ".html", ".jinja", ".j2", ".txt", ".env"}
CONFIG_NAMES = {"Makefile", "Dockerfile", "Procfile", "Justfile", "Taskfile"}
DOC_SUFFIXES = {".md", ".rst"}

# Names that frameworks commonly call by convention.
CONVENTION_PREFIXES = ("pytest_", "setup_", "teardown_", "visit_", "depart_", "do_",
                       "clean_", "on_", "handle_")
CONVENTION_SUFFIXES = ("_hook", "_handler", "_callback", "_receiver")
CONVENTION_NAMES = {"main", "handler", "lambda_handler", "create_app", "application",
                    "app", "load_tests", "setup", "teardown", "hook", "plugin", "register"}
# Module names that frameworks discover by convention (Django, Celery, ...).
CONVENTION_MODULES = {"admin", "apps", "models", "urls", "views", "signals", "tasks",
                      "receivers", "handlers", "plugins", "settings", "wsgi", "asgi",
                      "celery", "conftest"}

IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
NOQA = re.compile(r"#\s*(noqa|reaper)", re.IGNORECASE)
MAX_TEXT_FILE_BYTES = 2_000_000


@dataclass
class ScanResult:
    root: str
    mode: str                         # "app" or "library"
    files_scanned: int
    has_tests: bool
    removals: list[Removal]
    test_only: list[TestOnly]
    protected: list[tuple[str, str]]  # (key, reason)
    parse_errors: list[str]
    sources: dict[str, str]           # relative path -> source text (Python files)

    def removal(self, key: str) -> Removal | None:
        return next((r for r in self.removals if r.key == key), None)


def is_test_file(rel: str) -> bool:
    p = Path(rel)
    return (p.name.startswith("test_") or p.name.endswith("_test.py")
            or p.name == "conftest.py"
            or any(part in ("tests", "test") for part in p.parts[:-1]))


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        node = node.func
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _is_pure(node: ast.AST | None) -> bool:
    """True if evaluating the expression can't have side effects."""
    if node is None:
        return False
    if isinstance(node, (ast.Constant, ast.Name)):
        return True
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_is_pure(e) for e in node.elts)
    if isinstance(node, ast.Dict):
        return all(k is None or _is_pure(k) for k in node.keys) and all(_is_pure(v) for v in node.values)
    if isinstance(node, ast.JoinedStr):
        return all(_is_pure(v) for v in node.values)
    if isinstance(node, ast.FormattedValue):
        return _is_pure(node.value)
    if isinstance(node, ast.UnaryOp):
        return _is_pure(node.operand)
    if isinstance(node, ast.BinOp):
        return _is_pure(node.left) and _is_pure(node.right)
    return False


def _module_name(rel: str, package_dirs: set[str]) -> str:
    """Dotted import name of a file, given which directories are packages."""
    parts = list(Path(rel).with_suffix("").parts)
    # Walk up while the parent directory is a package.
    idx = len(parts) - 1
    while idx > 0 and "/".join(parts[:idx]) in package_dirs:
        idx -= 1
    mod = parts[idx:]
    if mod and mod[-1] == "__init__":
        mod = mod[:-1]
    return ".".join(mod)


class _File:
    """Everything learned from one Python file."""

    def __init__(self, rel: str, source: str, tree: ast.Module, module: str):
        self.rel = rel
        self.source = source
        self.lines = source.splitlines()
        self.tree = tree
        self.module = module
        self.is_test = is_test_file(rel)
        self.is_init = Path(rel).name == "__init__.py"
        self.definitions: list[tuple[Removal, list[str], str | None]] = []  # (removal, decorators, parent)
        self.class_bases: dict[str, list[str]] = {}
        self.refs: list[tuple[str, int]] = []         # names used (Name loads, attributes)
        self.import_refs: list[tuple[str, int]] = []  # names brought in by `from x import name`
        self.module_refs: list[tuple[str, int]] = []  # dotted modules imported
        self.string_refs: list[tuple[str, int]] = []
        self.dynamic_prefixes: set[str] = set()
        self.uses_dynamic_lookup = False
        self.has_main_guard = False
        self.imports: list[Removal] = []
        self.variables: list[Removal] = []
        self.unreachable: list[Removal] = []
        self.protected_imports: list[tuple[str, str]] = []

    def span_with_comments(self, node) -> int:
        start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
        col, i = node.col_offset, start - 2
        while i >= 0:
            line = self.lines[i]
            if line.strip().startswith("#") and len(line) - len(line.lstrip()) == col:
                start, i = i + 1, i - 1
            else:
                break
        return start

    def has_noqa(self, node) -> bool:
        return any(NOQA.search(self.lines[i - 1]) for i in range(node.lineno, node.end_lineno + 1)
                   if i - 1 < len(self.lines))


def _analyze_file(f: _File):
    tree = f.tree
    # --- definitions (module level and inside classes) -----------------
    def collect(body, prefix, parent):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qual = prefix + node.name
                if isinstance(node, ast.ClassDef):
                    kind = "class"
                    f.class_bases[qual] = [_dotted(b) for b in node.bases]
                else:
                    kind = "method" if parent else "function"
                r = Removal(key=f"{f.rel}::{qual}", kind=kind, name=qual, path=f.rel,
                            start=f.span_with_comments(node), end=node.end_lineno,
                            col=node.col_offset)
                f.definitions.append((r, [_dotted(d) for d in node.decorator_list], parent))
                if isinstance(node, ast.ClassDef):
                    collect(node.body, qual + ".", qual)
    collect(tree.body, "", None)

    # --- docstrings are not string references --------------------------
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            b = node.body
            if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) \
                    and isinstance(b[0].value.value, str):
                docstrings.add(id(b[0].value))

    # --- references, imports, dynamic lookups ---------------------------
    pkg_parts = f.module.split(".") if f.module else []
    package = pkg_parts if f.is_init else pkg_parts[:-1]
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    def inside(node, types):
        p = parents.get(node)
        while p is not None:
            if isinstance(p, types):
                return True
            p = parents.get(p)
        return False

    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Store):
            f.refs.append((node.id, line))
        elif isinstance(node, ast.Attribute):
            f.refs.append((node.attr, line))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings and len(node.value) <= 500:
                f.string_refs.extend((tok, line) for tok in IDENT.findall(node.value))
        elif isinstance(node, ast.Call):
            name = _dotted(node.func).split(".")[-1]
            if name in DYNAMIC_CALLS:
                literal = name in ("getattr", "hasattr") and len(node.args) > 1 \
                    and isinstance(node.args[1], ast.Constant)
                if not literal:
                    f.uses_dynamic_lookup = True
            if name in ("startswith", "endswith") and node.args and \
                    isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                _add_prefix(f, node.args[0].value)
        elif isinstance(node, ast.If) and _is_main_guard(node.test):
            f.has_main_guard = True
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add) and \
                isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
            _add_prefix(f, node.left.value)
        if isinstance(node, ast.JoinedStr) and len(node.values) > 1 and \
                isinstance(node.values[0], ast.Constant):
            _add_prefix(f, str(node.values[0].value))

        if isinstance(node, (ast.Import, ast.ImportFrom)):
            _collect_import(f, node, package, inside)

    _collect_unreachable(f, tree)
    if not f.is_test:
        _collect_variables(f, tree)


def _is_main_guard(test) -> bool:
    return (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name)
            and test.left.id == "__name__" and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value == "__main__")


def _add_prefix(f: _File, text: str):
    m = re.search(r"([A-Za-z_][A-Za-z0-9_]*)$", text)
    if m and len(m.group(1)) >= 3:
        f.dynamic_prefixes.add(m.group(1))


def _collect_import(f: _File, node, package: list[str], inside):
    if isinstance(node, ast.Import):
        for a in node.names:
            f.module_refs.append((a.name, node.lineno))
        aliases = [(a.name, a.asname) for a in node.names]
        module, level, is_from = None, 0, False
    else:
        level = node.level or 0
        base = package[:len(package) - (level - 1)] if level else []
        mod = ".".join([*base, *(node.module.split(".") if node.module else [])])
        if mod:
            f.module_refs.append((mod, node.lineno))
        for a in node.names:
            f.import_refs.append((a.name, node.lineno))
            if a.name != "*":
                f.module_refs.append((f"{mod}.{a.name}" if mod else a.name, node.lineno))
        aliases = [(a.name, a.asname) for a in node.names]
        module, is_from = node.module, True

    if f.is_test:
        return  # test files are never changed
    reason = None
    if is_from and node.module == "__future__":
        reason = "__future__ import"
    elif any(a[0] == "*" for a in aliases):
        reason = "star import"
    elif inside(node, (ast.Try,)):
        reason = "import inside try (optional dependency)"
    elif f.has_noqa(node):
        reason = "marked with # noqa"
    info = {"is_from": is_from, "module": module, "level": level,
            "aliases": [list(a) for a in aliases], "stmt_start": node.lineno,
            "stmt_end": node.end_lineno, "col": node.col_offset}
    for name, asname in aliases:
        bound = asname or (name if is_from else name.split(".")[0])
        key = f"{f.rel}::import {bound}@{node.lineno}"
        if reason:
            f.protected_imports.append((key, reason))
            continue
        shown = f"from {'.' * level}{module or ''} import {name}" if is_from else f"import {name}"
        if asname:
            shown += f" as {asname}"
        r = Removal(key=key, kind="import", name=shown, path=f.rel, start=node.lineno,
                    end=node.end_lineno, col=node.col_offset, confidence=95,
                    reasons=["imported name is never used"],
                    import_info={**info, "drop": name, "bound": bound})
        stdlib = getattr(sys, "stdlib_module_names", set())
        if not is_from and name.split(".")[0] not in stdlib:
            r.confidence -= 20
            r.reasons.append("a plain import may be there for its side effects")
        f.imports.append(r)


def _collect_unreachable(f: _File, tree):
    def walk_block(stmts):
        for i, s in enumerate(stmts):
            if isinstance(s, (ast.Return, ast.Raise, ast.Continue, ast.Break)) and i < len(stmts) - 1:
                first, last = stmts[i + 1], stmts[-1]
                start = f.span_with_comments(first)
                kw = type(s).__name__.lower()
                f.unreachable.append(Removal(
                    key=f"{f.rel}::unreachable@{start}", kind="unreachable",
                    name=f"code after {kw} (line {s.lineno})", path=f.rel, start=start,
                    end=last.end_lineno, col=first.col_offset, confidence=98,
                    reasons=[f"follows a {kw} statement, so it can never run"]))
                break
            if isinstance(s, (ast.If, ast.While)) and isinstance(s.test, ast.Constant) \
                    and not s.test.value and not s.orelse:
                start = f.span_with_comments(s)
                f.unreachable.append(Removal(
                    key=f"{f.rel}::unreachable@{start}", kind="unreachable",
                    name=f"`{type(s).__name__.lower()} {s.test.value!r}:` block (line {s.lineno})",
                    path=f.rel, start=start, end=s.end_lineno, col=s.col_offset,
                    confidence=98, reasons=["its condition is always false"]))
                continue
            for attr in ("body", "orelse", "finalbody"):
                block = getattr(s, attr, None)
                if isinstance(block, list) and block and isinstance(block[0], ast.stmt):
                    walk_block(block)
            for h in getattr(s, "handlers", []) or []:
                walk_block(h.body)
            for c in getattr(s, "cases", []) or []:
                walk_block(c.body)
    walk_block(tree.body)


def _collect_variables(f: _File, tree):
    def functions(body, prefix):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield node, prefix + node.name
                yield from functions(node.body, prefix + node.name + ".")
            elif isinstance(node, ast.ClassDef):
                yield from functions(node.body, prefix + node.name + ".")

    for fn, qual in functions(tree.body, ""):
        loads, declared, dynamic = set(), set(), False
        for n in ast.walk(fn):
            if isinstance(n, ast.Name) and not isinstance(n.ctx, ast.Store):
                loads.add(n.id)
            elif isinstance(n, (ast.Global, ast.Nonlocal)):
                declared.update(n.names)
            elif isinstance(n, ast.Call) and _dotted(n.func) in ("locals", "vars", "eval", "exec"):
                dynamic = True
        if dynamic:
            continue

        def own_statements(stmts):
            for s in stmts:
                if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                yield s
                for attr in ("body", "orelse", "finalbody"):
                    block = getattr(s, attr, None)
                    if isinstance(block, list) and block and isinstance(block[0], ast.stmt):
                        yield from own_statements(block)
                for h in getattr(s, "handlers", []) or []:
                    yield from own_statements(h.body)

        for s in own_statements(fn.body):
            target = value = None
            if isinstance(s, ast.Assign) and len(s.targets) == 1 and isinstance(s.targets[0], ast.Name):
                target, value = s.targets[0].id, s.value
            elif isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name) and s.value is not None:
                target, value = s.target.id, s.value
            if target is None or target.startswith("_") or target in loads or target in declared:
                continue
            if not _is_pure(value):
                continue
            f.variables.append(Removal(
                key=f"{f.rel}::{qual}:var:{target}@{s.lineno}", kind="variable",
                name=f"{target} in {qual}()", path=f.rel, start=s.lineno, end=s.end_lineno,
                col=s.col_offset, confidence=92,
                reasons=["assigned a value that is never read"]))


def scan(root: str | Path, mode: str = "app", excludes: list[str] | None = None) -> ScanResult:
    """Scan a project and return its dead code."""
    root = Path(root).resolve()
    excludes = excludes or []
    py_files: list[tuple[str, str]] = []
    parse_errors: list[str] = []
    config_tokens: dict[str, str] = {}
    doc_tokens: set[str] = set()

    for path in sorted(root.rglob("*")):
        relp = path.relative_to(root)
        rel = relp.as_posix()
        if any(part in EXCLUDED_DIRS for part in relp.parts) or \
                any(fnmatch.fnmatch(rel, pat) for pat in excludes) or not path.is_file():
            continue
        if path.suffix == ".py":
            try:
                py_files.append((rel, path.read_text(encoding="utf-8")))
            except (UnicodeDecodeError, OSError) as exc:
                parse_errors.append(f"{rel}: {exc}")
        elif path.suffix in CONFIG_SUFFIXES or path.name in CONFIG_NAMES or path.suffix in DOC_SUFFIXES:
            if path.stat().st_size > MAX_TEXT_FILE_BYTES:
                continue
            try:
                tokens = set(IDENT.findall(path.read_text(encoding="utf-8")))
            except (UnicodeDecodeError, OSError):
                continue
            if path.suffix in DOC_SUFFIXES:
                doc_tokens |= tokens
            else:
                for tok in tokens:
                    config_tokens.setdefault(tok, rel)

    package_dirs = {str(Path(rel).parent.as_posix()) for rel, _ in py_files
                    if Path(rel).name == "__init__.py"}
    files: list[_File] = []
    for rel, source in py_files:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # the project's own warnings aren't ours to show
                tree = ast.parse(source, filename=rel)
        except (SyntaxError, ValueError) as exc:
            parse_errors.append(f"{rel}: {exc}")
            continue
        f = _File(rel, source, tree, _module_name(rel, package_dirs))
        _analyze_file(f)
        files.append(f)
    return _classify(root, mode, files, package_dirs, config_tokens, doc_tokens, parse_errors)


def _classify(root, mode, files, package_dirs, config_tokens, doc_tokens, parse_errors) -> ScanResult:
    by_rel = {f.rel: f for f in files}
    project_classes = {r.name.split(".")[-1] for f in files for r, _, _ in f.definitions
                       if r.kind == "class"}
    any_dynamic = any(f.uses_dynamic_lookup for f in files)
    prefixes = set().union(*(f.dynamic_prefixes for f in files)) if files else set()
    has_tests = any(f.is_test for f in files)

    # Index references by name, with their location.
    name_refs: dict[str, list[tuple[str, int]]] = {}
    string_refs: dict[str, list[tuple[str, int]]] = {}
    module_refs: dict[str, list[tuple[str, int]]] = {}
    for f in files:
        for n, line in f.refs + f.import_refs:
            name_refs.setdefault(n, []).append((f.rel, line))
        for n, line in f.string_refs:
            string_refs.setdefault(n, []).append((f.rel, line))
        for m, line in f.module_refs:
            module_refs.setdefault(m, []).append((f.rel, line))

    protected: list[tuple[str, str]] = []
    pending_defs: list[Removal] = []
    for f in files:
        protected.extend(f.protected_imports)
        for r, decorators, parent in f.definitions:
            reason = _protect_definition(r, f, decorators, parent, string_refs, config_tokens,
                                         project_classes, mode)
            if reason:
                protected.append((r.key, reason))
            else:
                pending_defs.append(r)

    pending_modules: list[Removal] = []
    for f in files:
        reason = _protect_module(f, package_dirs, string_refs, config_tokens, mode)
        if reason:
            continue  # most files are not module candidates; don't list them all
        n = len(f.lines) or 1
        pending_modules.append(Removal(key=f.rel, kind="module", name=f.module or f.rel,
                                       path=f.rel, start=1, end=n, col=0, confidence=80,
                                       reasons=["nothing imports this module"]))

    pending_imports: list[Removal] = []
    for f in files:
        for r in f.imports:
            if mode == "library" and f.is_init:
                protected.append((r.key, "re-export in a library's __init__"))
            else:
                pending_imports.append(r)

    # Unreachable code and unused variables are dead regardless of anything else.
    dead: dict[str, Removal] = {}
    for f in files:
        if f.is_test:
            continue
        for r in f.unreachable + f.variables:
            dead[r.key] = r
    test_only: dict[str, TestOnly] = {}
    dead_spans: list[tuple[str, int, int, str]] = [(r.path, r.start, r.end, r.key) for r in dead.values()]
    ever_referenced: set[str] = set()

    def live(locs, own: Removal):
        out, via = [], set()
        for rel, line in locs:
            if rel == own.path and own.start <= line <= own.end:
                continue
            owner = next((k for p, s, e, k in dead_spans if p == rel and s <= line <= e and k != own.key), None)
            if owner:
                via.add(owner)
                continue
            out.append((rel, line))
        return out, via

    changed = True
    while changed:
        changed = False
        for r in pending_defs:
            if r.key in dead or r.key in test_only:
                continue
            locs = name_refs.get(r.name.split(".")[-1], [])
            refs, via = live(locs, r)
            if refs and all(by_rel[rel].is_test for rel, _ in refs):
                test_only[r.key] = TestOnly(r.key, r.kind, r.name, r.path, r.start, r.end,
                                            sorted({rel for rel, _ in refs}))
                continue
            if not refs:
                if via:
                    ever_referenced.add(r.key)
                r.used_by = sorted(via)
                dead[r.key] = r
                dead_spans.append((r.path, r.start, r.end, r.key))
                changed = True
        for r in pending_imports:
            if r.key in dead:
                continue
            f = by_rel[r.path]
            bound = r.import_info["bound"]
            locs = [(f.rel, line) for n, line in f.refs if n == bound]
            locs += [(f.rel, line) for n, line in f.string_refs if n == bound]
            if f.is_init:  # re-exports used elsewhere: `from pkg import name`
                locs += [(rel, line) for rel, line in name_refs.get(bound, []) if rel != f.rel]
            refs, via = live(locs, r)
            if not refs:
                r.used_by = sorted(via)
                dead[r.key] = r
                dead_spans.append((r.path, r.start, r.end, r.key))
                changed = True
        for r in pending_modules:
            if r.key in dead or r.key in test_only:
                continue
            f = by_rel[r.path]
            stem = Path(r.path).stem
            locs = list(module_refs.get(f.module, []))
            locs += [loc for loc in name_refs.get(stem, []) if loc[0] != r.path]
            refs, via = live(locs, r)
            if refs and all(by_rel[rel].is_test for rel, _ in refs):
                test_only[r.key] = TestOnly(r.key, "module", r.name, r.path, r.start, r.end,
                                            sorted({rel for rel, _ in refs}))
                continue
            if not refs:
                r.used_by = sorted(via)
                dead[r.key] = r
                dead_spans.append((r.path, r.start, r.end, r.key))
                changed = True

    # A dead module's own contents are deleted with it: drop them as separate removals.
    dead_modules = {r.path for r in dead.values() if r.kind == "module"}
    removals = [r for r in dead.values() if r.kind == "module" or r.path not in dead_modules]
    test_only_modules = {t.path for t in test_only.values() if t.kind == "module"}
    test_only_list = [t for t in test_only.values()
                      if (t.kind == "module" or t.path not in test_only_modules)
                      and not any(r.path == t.path and r.start <= t.start and t.end <= r.end
                                  for r in removals)]  # deleted along with a removal anyway

    # Containment: if an inner removal is kept, the removal containing it must be kept.
    for outer in removals:
        for inner in removals:
            if inner is not outer and inner.path == outer.path and outer.start <= inner.start \
                    and inner.end <= outer.end and (inner.start, inner.end) != (outer.start, outer.end):
                if inner.key not in outer.used_by:
                    outer.used_by.append(inner.key)
    keys = {r.key for r in removals}
    for r in removals:
        r.used_by = sorted(k for k in r.used_by if k in keys)

    for r in removals:
        _score(r, by_rel[r.path], prefixes, any_dynamic, doc_tokens, r.key in ever_referenced)

    removals.sort(key=lambda r: (r.path, r.start, r.key))
    return ScanResult(
        root=str(root), mode=mode, files_scanned=len(files), has_tests=has_tests,
        removals=removals, test_only=sorted(test_only_list, key=lambda t: (t.path, t.start)),
        protected=protected, parse_errors=parse_errors,
        sources={f.rel: f.source for f in files},
    )


def _is_public(r: Removal) -> bool:
    return not any(p.startswith("_") and not (p.startswith("__") and p.endswith("__"))
                   for p in [*Path(r.path).with_suffix("").parts, *r.name.split(".")])


def _protect_definition(r, f, decorators, parent, string_refs, config_tokens,
                        project_classes, mode) -> str | None:
    name = r.name.split(".")[-1]
    if f.is_test:
        return "defined in a test file"
    if name.startswith("__") and name.endswith("__"):
        return "dunder name (Python calls it implicitly)"
    for dec in decorators:
        if dec.endswith((".setter", ".getter", ".deleter")):
            return "property accessor"
        if dec not in SAFE_DECORATORS:
            return f"decorated with @{dec} (may be registered somewhere)"
    if parent:
        external = [b for b in f.class_bases.get(parent, []) if b and b.split(".")[-1]
                    not in project_classes and b not in ("object", "Generic", "Protocol")]
        if external:
            return f"method of a class based on {external[0]} (may override a hook)"
    hits = [loc for loc in string_refs.get(name, [])
            if not (loc[0] == r.path and r.start <= loc[1] <= r.end)]
    if hits:
        return f"name appears in a string at {hits[0][0]}:{hits[0][1]}"
    if name in config_tokens:
        return f"name appears in {config_tokens[name]}"
    if mode == "library" and _is_public(r):
        return "public name in library mode"
    return None


def _protect_module(f: _File, package_dirs, string_refs, config_tokens, mode) -> str | None:
    p = Path(f.rel)
    if f.is_test or f.is_init or p.name == "__main__.py":
        return "special file"
    if p.parent.as_posix() not in package_dirs:
        return "not inside a package (may be run as a script)"
    if f.has_main_guard:
        return "has an `if __name__ == '__main__'` block"
    if "migrations" in p.parts:
        return "migration files are discovered by the framework"
    if p.stem in string_refs or p.stem in config_tokens or f.module in config_tokens:
        return "module name appears in a string or config file"
    if mode == "library" and not p.stem.startswith("_"):
        return "public module in library mode"
    return None


def _score(r: Removal, f: _File, prefixes, any_dynamic, doc_tokens, cascaded: bool):
    if r.kind not in DEFINITION_KINDS and r.kind != "module":
        return  # imports, variables and unreachable code keep their own scores
    name = r.name.split(".")[-1] if r.kind != "module" else Path(r.path).stem
    conf = 90 if r.kind != "module" else 80
    reasons = list(r.reasons) if r.kind == "module" else ["no references found outside its own body"]
    if cascaded:
        reasons = ["only used by other dead code"]
    if r.kind != "module" and name.startswith("_"):
        conf += 5
        reasons.append("private name")
    if r.kind == "method":
        conf -= 10
        reasons.append("methods can be called dynamically")
    match = [p for p in prefixes if name.startswith(p) and name != p]
    if match:
        conf -= 50
        reasons.append(f"name matches a dynamic lookup pattern '{match[0]}*'")
    if r.kind == "module":
        if any_dynamic:
            conf -= 30
            reasons.append("the project loads some code by name at runtime")
        if name in CONVENTION_MODULES:
            conf -= 40
            reasons.append(f"frameworks often discover `{name}.py` modules by convention")
        hooks = [d.name for d, _, _ in f.definitions if d.kind == "function" and
                 (d.name in CONVENTION_NAMES or d.name.startswith(CONVENTION_PREFIXES))]
        if hooks:
            conf -= 40
            reasons.append(f"defines framework hook functions (e.g. {hooks[0]}), "
                           "so it may be loaded as a plugin")
    else:
        if f.uses_dynamic_lookup:
            conf -= 20
            reasons.append("its file looks names up at runtime (getattr/globals/importlib)")
        elif any_dynamic:
            conf -= 10
            reasons.append("the project looks names up at runtime elsewhere")
        if name in CONVENTION_NAMES or name.startswith(CONVENTION_PREFIXES) or \
                name.endswith(CONVENTION_SUFFIXES):
            conf -= 45
            reasons.append("name follows a framework convention, so it may be called by name")
    if name in doc_tokens:
        conf -= 20
        reasons.append("mentioned in the documentation")
    r.confidence = max(0, min(100, conf))
    r.reasons = reasons


def guess_mode(root: str | Path) -> tuple[str, str]:
    """Guess whether a project is an application or a library, with a reason."""
    root = Path(root)
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"^\s*classifiers\s*=", text, re.M) or "[project.urls]" in text:
            return "library", "pyproject.toml has publishing metadata (classifiers or URLs)"
    if (root / "setup.py").exists() or (root / "setup.cfg").exists():
        return "library", "the project has a setup.py or setup.cfg"
    return "app", "no publishing metadata found"
