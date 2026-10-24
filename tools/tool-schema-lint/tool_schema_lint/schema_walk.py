"""Iterative traversal of JSON Schema documents.

The walker visits every subschema reachable through structural keywords, but never
follows `$ref`. That keeps cyclic or recursive schemas from looping forever; reference
targets are checked separately with `resolve_ref`.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

# Keywords whose value is a single subschema.
_SINGLE = ("items", "additionalProperties", "not", "if", "then", "else", "contains",
           "propertyNames", "unevaluatedProperties", "unevaluatedItems", "additionalItems")
# Keywords whose value is a list of subschemas.
_LIST = ("anyOf", "oneOf", "allOf", "prefixItems")
# Keywords whose value is a map of name -> subschema.
_MAP = ("properties", "patternProperties", "$defs", "definitions", "dependentSchemas")

# Hops that count as one level of data nesting (used for OpenAI's depth limit).
_NESTING = {"properties", "items", "prefixItems", "additionalProperties", "patternProperties"}


@dataclass(frozen=True)
class Node:
    schema: Any
    segments: tuple[str | int, ...]  # path from the schema root
    depth: int  # data nesting depth; the root object is 0
    property_name: str | None  # set when this node is the schema of an object property


def walk(root: Any) -> Iterator[Node]:
    """Yield every subschema of `root` (including `root` itself) in document order."""
    stack: list[Node] = [Node(root, (), 0, None)]
    while stack:
        node = stack.pop()
        yield node
        schema = node.schema
        if not isinstance(schema, dict):
            continue
        children: list[Node] = []
        for key in _SINGLE:
            child = schema.get(key)
            if isinstance(child, dict):
                children.append(_child(node, child, (key,), key, None))
            elif key == "items" and isinstance(child, list):  # draft-07 tuple form
                children.extend(_child(node, c, (key, i), key, None) for i, c in enumerate(child))
        for key in _LIST:
            value = schema.get(key)
            if isinstance(value, list):
                children.extend(_child(node, c, (key, i), key, None) for i, c in enumerate(value))
        for key in _MAP:
            value = schema.get(key)
            if isinstance(value, dict):
                children.extend(
                    _child(node, c, (key, name), key, name if key == "properties" else None)
                    for name, c in value.items()
                )
        stack.extend(reversed(children))


def _child(parent: Node, schema: Any, segs: tuple[str | int, ...], key: str, prop: str | None) -> Node:
    if key in ("$defs", "definitions"):
        depth = 0  # definitions are reusable roots
    else:
        depth = parent.depth + (1 if key in _NESTING else 0)
    return Node(schema, parent.segments + segs, depth, prop)


def resolve_ref(root: Any, ref: str) -> tuple[bool, str]:
    """Check whether a `$ref` points at something inside `root`.

    Returns (ok, reason). Only document-local references ("#" or "#/...") can be checked;
    anything else is reported as not resolvable offline.
    """
    if ref == "#":
        return True, ""
    if not ref.startswith("#/"):
        return False, "only local references ('#/...') can be resolved offline"
    target = root
    for raw in ref[2:].split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(target, dict) and part in target:
            target = target[part]
        elif isinstance(target, list) and part.isdigit() and int(part) < len(target):
            target = target[int(part)]
        else:
            return False, f"'{part}' does not exist"
    return True, ""
