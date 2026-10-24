"""Explicit tool registry. Never expose arbitrary shell, filesystem, or code execution."""
import ast
import operator
from datetime import datetime, timezone
from typing import Any

from .memory import MemoryStore
from .models import ToolSpec

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def safe_calculate(expression: str) -> str:
    if len(expression) > 100:
        raise ValueError("Expression is too long.")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("Invalid arithmetic expression.") from exc

    def visit(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            if abs(node.value) > 10**12:
                raise ValueError("Number is out of bounds.")
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 8:
                raise ValueError("Exponent is out of bounds.")
            result = _ALLOWED_BINOPS[type(node.op)](left, right)
            if abs(result) > 10**15:
                raise ValueError("Result is out of bounds.")
            return result
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY:
            return _ALLOWED_UNARY[type(node.op)](visit(node.operand))
        raise ValueError("Only basic arithmetic is supported.")
    return str(visit(tree))


def build_tools(memory: MemoryStore, user_id: str) -> dict[str, ToolSpec]:
    def calculate(args: dict) -> str:
        return safe_calculate(args["expression"])

    def utc_time(_: dict) -> str:
        return datetime.now(timezone.utc).isoformat()

    def remember(args: dict) -> str:
        fact = args["fact"].strip()
        lowered = fact.casefold()
        sensitive_markers = ("api_key=", "api key:", "password=", "password:", "access_token=", "secret=")
        if any(marker in lowered for marker in sensitive_markers) or "sk-" in lowered:
            raise ValueError("Memory refused: do not store credentials or secrets.")
        memory.remember(user_id, fact)
        return "Saved one user-scoped memory fact."

    return {
        "calculator": ToolSpec(
            name="calculator",
            description="Evaluate a simple arithmetic expression. No variables or functions.",
            parameters={
                "type": "object",
                "properties": {"expression": {"type": "string", "maxLength": 100}},
                "required": ["expression"],
                "additionalProperties": False,
            },
            handler=calculate,
        ),
        "get_utc_time": ToolSpec(
            name="get_utc_time",
            description="Return the current UTC time.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            handler=utc_time,
        ),
        "remember_fact": ToolSpec(
            name="remember_fact",
            description="Save a non-sensitive, durable fact to this user's local memory. Never save secrets.",
            parameters={
                "type": "object",
                "properties": {"fact": {"type": "string", "minLength": 1, "maxLength": 500}},
                "required": ["fact"],
                "additionalProperties": False,
            },
            handler=remember,
        ),
    }
