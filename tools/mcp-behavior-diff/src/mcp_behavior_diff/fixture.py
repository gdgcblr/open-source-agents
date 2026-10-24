"""Fixture loading with strict, fail-closed validation.

A fixture is *code*: it names a command that will be executed on your machine.
Only run fixtures you would be willing to run as a shell script. Validation here
guards against accidents and unsafe defaults, not against a malicious fixture.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import FixtureError

MAX_FIXTURE_BYTES = 256 * 1024

# Hard ceilings: a fixture may lower limits but never raise them past these.
CEILING_CALL_TIMEOUT_S = 120.0
CEILING_STARTUP_TIMEOUT_S = 120.0
CEILING_MAX_CALLS = 200
CEILING_MAX_OUTPUT_BYTES = 1024 * 1024
CEILING_MAX_ARG_BYTES = 64 * 1024

_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_TOOL_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SHELL_META_RE = re.compile(r"[;|&$`<>\n\r\x00]")
SECRET_NAME_RE = re.compile(r"KEY|TOKEN|SECRET|PASSW|CREDENTIAL|AUTH|COOKIE|SESSION", re.I)
# Variables that change how a process loads code; never settable from a fixture.
_FORBIDDEN_ENV_RE = re.compile(r"^(LD_.*|DYLD_.*|PATH|BASH_ENV|ENV|NODE_OPTIONS|PYTHONSTARTUP|PYTHONHOME)$")
_SERVER_LABELS = ("old", "new")


@dataclass(frozen=True)
class Limits:
    call_timeout_s: float = 10.0
    startup_timeout_s: float = 20.0
    max_calls: int = 50
    max_output_bytes: int = 64 * 1024
    max_arg_bytes: int = 16 * 1024


@dataclass(frozen=True)
class ServerSpec:
    command: str
    args: tuple[str, ...] = ()
    cwd: Path | None = None  # always set by the loader
    env: dict[str, str] = field(default_factory=dict)
    env_passthrough: tuple[str, ...] = ()


@dataclass(frozen=True)
class Call:
    id: str
    tool: str
    arguments: dict[str, Any]
    read_only: bool


@dataclass(frozen=True)
class Fixture:
    path: Path
    servers: dict[str, ServerSpec]
    calls: tuple[Call, ...]
    limits: Limits


def _expect_mapping(value: Any, where: str, allowed: set[str], required: set[str] = frozenset()) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FixtureError(f"{where}: expected a mapping")
    unknown = set(value) - allowed
    if unknown:
        raise FixtureError(f"{where}: unknown key(s) {sorted(map(str, unknown))}; allowed: {sorted(allowed)}")
    missing = required - set(value)
    if missing:
        raise FixtureError(f"{where}: missing required key(s) {sorted(missing)}")
    return value


def _number(value: Any, where: str, ceiling: float, *, integer: bool = False) -> float:
    ok_type = int if integer else (int, float)
    if isinstance(value, bool) or not isinstance(value, ok_type):
        raise FixtureError(f"{where}: expected a {'whole ' if integer else ''}number")
    if value <= 0 or value > ceiling:
        raise FixtureError(f"{where}: must be > 0 and <= {ceiling:g} (hard ceiling)")
    return value


def _parse_limits(raw: Any) -> Limits:
    if raw is None:
        return Limits()
    data = _expect_mapping(raw, "limits", set(Limits.__dataclass_fields__))
    defaults = Limits()
    return Limits(
        call_timeout_s=float(_number(data.get("call_timeout_s", defaults.call_timeout_s), "limits.call_timeout_s", CEILING_CALL_TIMEOUT_S)),
        startup_timeout_s=float(_number(data.get("startup_timeout_s", defaults.startup_timeout_s), "limits.startup_timeout_s", CEILING_STARTUP_TIMEOUT_S)),
        max_calls=int(_number(data.get("max_calls", defaults.max_calls), "limits.max_calls", CEILING_MAX_CALLS, integer=True)),
        max_output_bytes=int(_number(data.get("max_output_bytes", defaults.max_output_bytes), "limits.max_output_bytes", CEILING_MAX_OUTPUT_BYTES, integer=True)),
        max_arg_bytes=int(_number(data.get("max_arg_bytes", defaults.max_arg_bytes), "limits.max_arg_bytes", CEILING_MAX_ARG_BYTES, integer=True)),
    )


def _str_list(value: Any, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) and "\x00" not in v for v in value):
        raise FixtureError(f"{where}: expected a list of strings")
    return tuple(value)


def _parse_server(label: str, raw: Any, base_dir: Path) -> ServerSpec:
    where = f"servers.{label}"
    data = _expect_mapping(raw, where, {"command", "args", "cwd", "env", "env_passthrough"}, {"command"})
    command = data["command"]
    if not isinstance(command, str) or not command.strip():
        raise FixtureError(f"{where}.command: expected a non-empty string")
    if _SHELL_META_RE.search(command) or (re.search(r"\s", command) and "/" not in command and "\\" not in command):
        raise FixtureError(
            f"{where}.command: must be a single executable (no shell syntax). Put arguments in `args`; no shell is ever used."
        )
    args = _str_list(data.get("args", []), f"{where}.args")

    cwd: Path = base_dir  # default: the fixture's own directory, never the caller's cwd
    if "cwd" in data:
        if not isinstance(data["cwd"], str):
            raise FixtureError(f"{where}.cwd: expected a string")
        cwd = (base_dir / data["cwd"]).resolve()
        if not cwd.is_dir():
            raise FixtureError(f"{where}.cwd: {cwd} is not a directory")
        if cwd != base_dir and base_dir not in cwd.parents:
            raise FixtureError(f"{where}.cwd: must stay inside the fixture directory ({base_dir})")

    env_raw = data.get("env", {})
    if not isinstance(env_raw, dict):
        raise FixtureError(f"{where}.env: expected a mapping")
    env: dict[str, str] = {}
    for name, value in env_raw.items():
        if not isinstance(name, str) or not _ENV_NAME_RE.match(name):
            raise FixtureError(f"{where}.env: invalid variable name {name!r}")
        if _FORBIDDEN_ENV_RE.match(name):
            raise FixtureError(f"{where}.env.{name}: not allowed (can change how code is loaded)")
        if SECRET_NAME_RE.search(name):
            raise FixtureError(
                f"{where}.env.{name}: looks like a secret. Never write secrets in a fixture; use `env_passthrough`."
            )
        if not isinstance(value, (str, int, float, bool)) or "\x00" in str(value):
            raise FixtureError(f"{where}.env.{name}: expected a scalar value")
        env[name] = str(value)

    passthrough = _str_list(data.get("env_passthrough", []), f"{where}.env_passthrough")
    for name in passthrough:
        if not _ENV_NAME_RE.match(name) or _FORBIDDEN_ENV_RE.match(name):
            raise FixtureError(f"{where}.env_passthrough: invalid or forbidden variable name {name!r}")
    return ServerSpec(command=command, args=args, cwd=cwd, env=env, env_passthrough=passthrough)


def _parse_call(index: int, raw: Any, limits: Limits) -> Call:
    where = f"calls[{index}]"
    data = _expect_mapping(raw, where, {"id", "tool", "arguments", "read_only"}, {"id", "tool", "read_only"})
    call_id, tool = data["id"], data["tool"]
    if not isinstance(call_id, str) or not _ID_RE.match(call_id):
        raise FixtureError(f"{where}.id: must match {_ID_RE.pattern}")
    if not isinstance(tool, str) or not _TOOL_RE.match(tool):
        raise FixtureError(f"{where}.tool: must match {_TOOL_RE.pattern}")
    if data["read_only"] is not True:
        raise FixtureError(
            f"{where}.read_only: must be `true`. You are asserting that calling `{tool}` has no side effects; "
            "tools you cannot vouch for must not be listed."
        )
    arguments = data.get("arguments", {})
    if not isinstance(arguments, dict):
        raise FixtureError(f"{where}.arguments: expected a mapping")
    try:
        encoded = json.dumps(arguments, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise FixtureError(f"{where}.arguments: must be JSON-serialisable ({exc})") from exc
    if len(encoded.encode("utf-8")) > limits.max_arg_bytes:
        raise FixtureError(f"{where}.arguments: larger than limits.max_arg_bytes ({limits.max_arg_bytes})")
    return Call(id=call_id, tool=tool, arguments=json.loads(encoded), read_only=True)


def load_fixture(path: str | Path) -> Fixture:
    """Load and validate a fixture. Raises FixtureError on any problem (fail closed)."""
    fixture_path = Path(path).resolve()
    if not fixture_path.is_file():
        raise FixtureError(f"fixture not found: {fixture_path}")
    if fixture_path.stat().st_size > MAX_FIXTURE_BYTES:
        raise FixtureError(f"fixture larger than {MAX_FIXTURE_BYTES} bytes")
    try:
        # safe_load only: never construct arbitrary Python objects from YAML tags.
        document = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise FixtureError(f"cannot parse fixture: {exc}") from exc

    data = _expect_mapping(document, "fixture", {"version", "servers", "calls", "limits"}, {"version", "servers", "calls"})
    if data["version"] != 1:
        raise FixtureError("fixture.version: only version 1 is supported")
    limits = _parse_limits(data.get("limits"))

    base_dir = fixture_path.parent
    servers_raw = _expect_mapping(data["servers"], "servers", set(_SERVER_LABELS), set(_SERVER_LABELS))
    servers = {label: _parse_server(label, servers_raw[label], base_dir) for label in _SERVER_LABELS}

    calls_raw = data["calls"]
    if not isinstance(calls_raw, list) or not calls_raw:
        raise FixtureError("calls: expected a non-empty list")
    if len(calls_raw) > limits.max_calls:
        raise FixtureError(f"calls: {len(calls_raw)} entries exceeds limits.max_calls ({limits.max_calls})")
    calls = tuple(_parse_call(i, raw, limits) for i, raw in enumerate(calls_raw))
    ids = [c.id for c in calls]
    if len(set(ids)) != len(ids):
        raise FixtureError("calls: duplicate id(s)")
    return Fixture(path=fixture_path, servers=servers, calls=calls, limits=limits)
