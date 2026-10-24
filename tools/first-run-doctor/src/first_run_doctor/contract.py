"""Small, explicit contracts. No README commands are inferred or executed."""

import hashlib
import json
import math
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

MAX_JSON_BYTES = 2 * 1024 * 1024
TYPES = {"string", "list", "object", "integer", "number", "boolean", "null"}


class DoctorError(ValueError):
    """Invalid configuration or an unsupported inspection operation."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DoctorError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise DoctorError(f"Non-finite JSON value: {value}")


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise DoctorError("JSON number exceeds finite floating-point range")
    return number


def parse_json(text):
    try:
        return json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except (ValueError, RecursionError) as exc:
        raise DoctorError(f"Invalid JSON: {exc}") from exc


def read_json(path, limit=MAX_JSON_BYTES):
    try:
        descriptor = os.open(
            path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        )
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise DoctorError("Expected a regular JSON file")
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise DoctorError(f"JSON file exceeds {limit} bytes")
        return parse_json(data.decode("utf-8"))
    except (OSError, UnicodeError) as exc:
        raise DoctorError(f"Cannot read JSON file: {exc}") from exc


def fingerprint(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def relative_path(value):
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 512
        or "\\" in value
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise DoctorError("Paths must be nonempty relative POSIX paths")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts) or PurePosixPath(value).is_absolute():
        raise DoctorError(f"Unsafe relative path: {value}")
    return value


def contained_file(root, value):
    """Reject symlinks in every component, including the final file."""
    relative_path(value)
    current = Path(root)
    for component in PurePosixPath(value).parts:
        current = current / component
        if current.is_symlink():
            raise DoctorError(f"Symlinks are unsupported: {value}")
    if not current.resolve().is_relative_to(Path(root).resolve()):
        raise DoctorError(f"Path escapes project: {value}")
    return current


def _keys(value, allowed, label):
    if not isinstance(value, dict) or set(value) - allowed:
        raise DoctorError(f"Invalid or unsupported keys in {label}")


def _paths(value, label):
    if not isinstance(value, list) or len(value) > 64:
        raise DoctorError(f"{label} must be a list with at most 64 entries")
    for item in value:
        relative_path(item)
    if len(set(value)) != len(value):
        raise DoctorError(f"Duplicate {label}")
    return value


@dataclass(frozen=True)
class Contract:
    data: dict
    path: str

    @property
    def digest(self):
        return fingerprint(self.data)

    @property
    def command(self):
        return self.data["command"]

    @property
    def artifacts(self):
        return self.data["artifacts"]


def load_contract(root, filename="doctor.json"):
    path = contained_file(root, filename)
    data = read_json(path, 65536)
    _keys(
        data,
        {"schema_version", "command", "inputs", "timeout_seconds", "required_env", "artifacts"},
        "contract",
    )
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise DoctorError("Only schema_version 1 is supported")
    command = data.get("command")
    if (
        not isinstance(command, list)
        or not 2 <= len(command) <= 64
        or any(not isinstance(x, str) or not x or "\x00" in x for x in command)
        or command[0] != "{python}"
    ):
        raise DoctorError("command must be an argument list starting with {python} and a script")
    entrypoint = relative_path(command[1])
    if not entrypoint.endswith(".py") or entrypoint.startswith("-"):
        raise DoctorError("v0.1 supports a local .py entrypoint, not -c/-m or shell commands")
    if any("{python}" in x for x in command[1:]):
        raise DoctorError("{python} is supported only as the first argument")
    inputs = _paths(data.setdefault("inputs", []), "inputs")
    timeout = data.setdefault("timeout_seconds", 10)
    if type(timeout) not in {int, float} or not 0.1 <= timeout <= 120 or not math.isfinite(timeout):
        raise DoctorError("timeout_seconds must be between 0.1 and 120")
    names = data.setdefault("required_env", [])
    if (
        not isinstance(names, list)
        or len(names) > 64
        or any(not isinstance(x, str) or not re.fullmatch(r"[A-Z_][A-Z0-9_]*", x) for x in names)
        or len(set(names)) != len(names)
    ):
        raise DoctorError("required_env must contain unique uppercase environment names")
    blocked = {
        "EXPERIENTIAL_API_KEY",
        "PATH",
        "HOME",
        "TMPDIR",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "LD_PRELOAD",
        "DYLD_INSERT_LIBRARIES",
    }
    if set(names) & blocked:
        raise DoctorError("required_env contains a reserved runner or Doctor variable")
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list) or not 1 <= len(artifacts) <= 32:
        raise DoctorError("Declare 1-32 JSON artifacts with behavioral checks")
    outputs = []
    protected = [entrypoint, filename, "pyproject.toml", "requirements.txt", *inputs]
    for artifact in artifacts:
        _keys(artifact, {"path", "format", "checks"}, "artifact")
        name = relative_path(artifact.get("path"))
        if any(name == p or p.startswith(name + "/") for p in protected):
            raise DoctorError(f"Output collides with a protected input: {name}")
        if any(name == p or name.startswith(p + "/") or p.startswith(name + "/") for p in outputs):
            raise DoctorError("Duplicate or overlapping artifact paths")
        outputs.append(name)
        if artifact.get("format") != "json":
            raise DoctorError("Only format=json artifacts are supported")
        checks = artifact.get("checks")
        if not isinstance(checks, list) or not 1 <= len(checks) <= 64:
            raise DoctorError("Each artifact needs 1-64 field checks")
        for check in checks:
            _keys(check, {"field", "type", "nonempty", "equals"}, "field check")
            if not isinstance(check.get("field"), str) or not 1 <= len(check["field"]) <= 128:
                raise DoctorError("Checks need a nonempty top-level field name")
            if not set(check) & {"type", "nonempty", "equals"}:
                raise DoctorError("A field name alone is not a behavioral assertion")
            if "type" in check and (
                not isinstance(check["type"], str) or check["type"] not in TYPES
            ):
                raise DoctorError("Unsupported field type")
            if "nonempty" in check and check["nonempty"] is not True:
                raise DoctorError("nonempty must be true when specified")
    return Contract(data, filename)
