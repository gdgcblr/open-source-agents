"""Python AST helpers: import alias resolution and enclosing-scope lookup."""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, field


def module_name_for(path: str) -> str:
    """'pkg/utils.py' -> 'pkg.utils'; 'pkg/__init__.py' -> 'pkg'."""
    parts = path.removesuffix(".py").replace("\\", "/").split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if parts and parts[0] in {"src", "lib"} and len(parts) > 1:
        parts = parts[1:]
    return ".".join(p for p in parts if p)


@dataclass
class ImportMap:
    module: str
    aliases: dict[str, str] = field(default_factory=dict)
    imported_modules: set[str] = field(default_factory=set)
    local_defs: set[str] = field(default_factory=set)

    @classmethod
    def build(cls, tree: ast.Module, module: str) -> ImportMap:
        im = cls(module=module)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    im.imported_modules.add(a.name)
                    if a.asname:
                        im.aliases[a.asname] = a.name
                    else:
                        root = a.name.split(".")[0]
                        im.aliases.setdefault(root, root)
            elif isinstance(node, ast.ImportFrom):
                base = _resolve_relative(module, node.module, node.level)
                if base:
                    im.imported_modules.add(base)
                for a in node.names:
                    full = f"{base}.{a.name}" if base else a.name
                    im.aliases[a.asname or a.name] = full
        for node in tree.body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                im.local_defs.add(node.name)
        return im

    def resolve(self, node: ast.AST) -> str | None:
        """Dotted, import-resolved name for Name/Attribute/Call chains."""
        if isinstance(node, ast.Name):
            if node.id in self.aliases:
                return self.aliases[node.id]
            if node.id in self.local_defs:
                return f"{self.module}.{node.id}" if self.module else node.id
            return node.id
        if isinstance(node, ast.Attribute):
            base = self.resolve(node.value)
            return f"{base}.{node.attr}" if base else None
        if isinstance(node, ast.Call):
            return self.resolve(node.func)
        if isinstance(node, ast.Subscript):
            return self.resolve(node.value)
        return None


def _resolve_relative(module: str, target: str | None, level: int) -> str:
    if level == 0:
        return target or ""
    parts = module.split(".")
    base = parts[: max(len(parts) - level, 0)]
    if target:
        base.append(target)
    return ".".join(base)


def name_matches(resolved: str, pattern: str) -> bool:
    """Exact match, or pattern matches the tail of a resolved name (flask.request.args)."""
    return resolved == pattern or resolved.endswith("." + pattern)


def is_constant(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.JoinedStr):
        return all(isinstance(v, ast.Constant) for v in node.values)
    if isinstance(node, ast.List | ast.Tuple | ast.Set):
        return all(is_constant(e) for e in node.elts)
    if isinstance(node, ast.BinOp):
        return is_constant(node.left) and is_constant(node.right)
    return False


def function_ranges(tree: ast.Module) -> list[tuple[int, int, ast.AST]]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            out.append((node.lineno, node.end_lineno or node.lineno, node))
    return out


def enclosing_function(
    ranges: list[tuple[int, int, ast.AST]], line: int
) -> tuple[int, int, ast.AST] | None:
    best = None
    for start, end, node in ranges:
        if start <= line <= end and (best is None or start >= best[0]):
            best = (start, end, node)
    return best


def stable_hash(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8", "replace"))
        h.update(b"\x00")
    return h.hexdigest()[:24]


def normalized_source(node: ast.AST) -> str:
    """Comment- and whitespace-insensitive source for content hashing."""
    return ast.unparse(node)
