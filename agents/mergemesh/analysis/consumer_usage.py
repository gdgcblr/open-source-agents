"""AST-based consumer source code scanner for REST JSON field accesses."""

from __future__ import annotations

import ast
from pathlib import Path

from domain.models import ConsumerFieldAccess


class ConsumerParseError(ValueError):
    """Raised when consumer source cannot be read or parsed."""


def _extract_subscript_chain(node: ast.AST) -> list[str] | None:
    """Resolve chained string subscripts like payload['customer']['id'] -> ['customer', 'id']."""
    parts: list[str] = []
    curr: ast.AST = node
    while isinstance(curr, ast.Subscript):
        slice_node = curr.slice
        # Python <3.9 compatibility just in case, though 3.10+ uses Constant directly
        if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
            parts.append(slice_node.value)
        else:
            return None
        curr = curr.value
    if not parts:
        return None
    parts.reverse()
    return parts


class _DictAccessVisitor(ast.NodeVisitor):
    def __init__(self, consumer_repo: str, file_path: str, source_lines: list[str]) -> None:
        self.consumer_repo = consumer_repo
        self.file_path = file_path
        self.source_lines = source_lines
        self.accesses: list[ConsumerFieldAccess] = []
        self._visited_subscripts: set[int] = set()

    def _get_line_snippet(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1].strip()
        return ""

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if id(node) in self._visited_subscripts:
            return
        chain = _extract_subscript_chain(node)
        if chain:
            # Mark inner subscripts as visited so we don't duplicate partial chains
            curr: ast.AST = node
            while isinstance(curr, ast.Subscript):
                self._visited_subscripts.add(id(curr))
                curr = curr.value
            field_path = ".".join(chain)
            lineno = getattr(node, "lineno", 1)
            self.accesses.append(
                ConsumerFieldAccess(
                    consumer_repo=self.consumer_repo,
                    file_path=self.file_path,
                    line=lineno,
                    field_path=field_path,
                    access_mode="subscript",
                    code_snippet=self._get_line_snippet(lineno),
                    default_provided=False,
                )
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Match `<obj>.get("field_name", [default])`
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and len(node.args) >= 1
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            key_name = node.args[0].value
            prefix_chain = _extract_subscript_chain(node.func.value)
            if prefix_chain:
                for sub_node in ast.walk(node.func.value):
                    if isinstance(sub_node, ast.Subscript):
                        self._visited_subscripts.add(id(sub_node))
                field_path = ".".join(prefix_chain + [key_name])
            else:
                field_path = key_name

            has_default = len(node.args) >= 2 and not (
                isinstance(node.args[1], ast.Constant) and node.args[1].value is None
            )
            lineno = getattr(node, "lineno", 1)
            self.accesses.append(
                ConsumerFieldAccess(
                    consumer_repo=self.consumer_repo,
                    file_path=self.file_path,
                    line=lineno,
                    field_path=field_path,
                    access_mode="get",
                    code_snippet=self._get_line_snippet(lineno),
                    default_provided=has_default,
                )
            )
        self.generic_visit(node)


def extract_consumer_field_accesses(
    source_code: str,
    consumer_repo: str = "checkout-client",
    rel_file_path: str = "repos/checkout-client/client.py",
) -> list[ConsumerFieldAccess]:
    """Parse Python consumer source code and return detected JSON/dict field accesses."""
    try:
        tree = ast.parse(source_code, filename=rel_file_path)
    except SyntaxError as exc:
        raise ConsumerParseError(
            f"Syntax error while parsing consumer source {rel_file_path} (line {exc.lineno}): {exc.msg}"
        ) from exc

    lines = source_code.splitlines()
    visitor = _DictAccessVisitor(consumer_repo=consumer_repo, file_path=rel_file_path, source_lines=lines)
    visitor.visit(tree)
    return visitor.accesses


def scan_consumer_file(
    file_path: Path,
    consumer_repo: str = "checkout-client",
    rel_file_path: str = "repos/checkout-client/client.py",
) -> list[ConsumerFieldAccess]:
    """Read a Python consumer file from disk and extract dict field accesses."""
    if not file_path.exists() or not file_path.is_file():
        raise ConsumerParseError(f"Consumer source file not found: {file_path}")
    try:
        source_code = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConsumerParseError(f"Unable to read consumer source {file_path}: {exc}") from exc

    return extract_consumer_field_accesses(
        source_code=source_code,
        consumer_repo=consumer_repo,
        rel_file_path=rel_file_path,
    )
