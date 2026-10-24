"""Guardrails: decide whether a call may run and what a child process may see."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .errors import PolicyViolation
from .fixture import SECRET_NAME_RE, Call, ServerSpec


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str


def decide_call(call: Call, annotations: Any | None) -> Decision:
    """Fail-closed gate for a single tool call.

    Annotations come from the server under test and may be wrong, so they can only
    *veto* a call. They never grant permission: the fixture's explicit
    `read_only: true` assertion is the grant (already enforced by the loader).
    """
    if not call.read_only:  # defence in depth; the loader already guarantees this
        return Decision(False, "fixture does not assert read_only")
    if getattr(annotations, "destructive_hint", None) is True:
        return Decision(False, "server declares this tool destructive (destructive_hint=true)")
    if getattr(annotations, "read_only_hint", None) is False:
        return Decision(False, "server declares this tool is not read-only (read_only_hint=false)")
    if getattr(annotations, "read_only_hint", None) is not True:
        return Decision(True, "allowed on fixture assertion only (server declares no read_only_hint)")
    return Decision(True, "allowed (fixture asserts read_only and server agrees)")


def build_child_env(
    spec: ServerSpec, parent_env: Mapping[str, str], allow_secret_env: frozenset[str] = frozenset()
) -> tuple[dict[str, str], tuple[str, ...]]:
    """Build the *extra* environment for the server process.

    The MCP SDK already starts children from a tiny allow-list (HOME, PATH, USER, ...),
    not from the full parent environment. We add only what the fixture lists explicitly.
    Returns (extra_env, secret_values). Secret values are later scrubbed from all output.
    """
    extra = dict(spec.env)
    secret_values: list[str] = []
    for name in spec.env_passthrough:
        if SECRET_NAME_RE.search(name) and name not in allow_secret_env:
            raise PolicyViolation(
                f"env_passthrough `{name}` looks like a secret; pass --allow-secret-env {name} to confirm you intend this"
            )
        if name not in parent_env:
            raise PolicyViolation(f"env_passthrough `{name}` is not set in your environment")
        extra[name] = parent_env[name]
        secret_values.append(parent_env[name])
    return extra, tuple(secret_values)
