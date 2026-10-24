"""Check observable output facts; no language model decides verification."""

import hashlib
import os
import stat

from .contract import MAX_JSON_BYTES, DoctorError, contained_file, parse_json


def observation(check_id, label, status, detail):
    return {"id": check_id, "label": label, "status": status, "detail": detail}


def matches_type(value, name):
    return {
        "string": type(value) is str,
        "list": type(value) is list,
        "object": type(value) is dict,
        "integer": type(value) is int,
        "number": type(value) in {int, float},
        "boolean": type(value) is bool,
        "null": value is None,
    }[name]


def equal_json(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(equal_json(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(equal_json(a, b) for a, b in zip(left, right))
    return left == right


def _read_regular(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise DoctorError("Expected a regular file")
        content = stream.read(MAX_JSON_BYTES + 1)
    if len(content) > MAX_JSON_BYTES:
        raise DoctorError("Artifact exceeds the 2 MiB verification read limit")
    return content


def verify_artifacts(workspace, contract):
    observations = []
    for index, artifact in enumerate(contract.artifacts, 1):
        prefix = f"A{index}"
        name = artifact["path"]
        checks = artifact["checks"]
        try:
            path = contained_file(workspace, name)
            if not path.exists():
                observations.append(
                    observation(prefix, f"Fresh {name}", "fail", "Expected artifact missing")
                )
                raise FileNotFoundError
            content = _read_regular(path)
            data = parse_json(content.decode("utf-8"))
            if not isinstance(data, dict):
                raise DoctorError("Expected a JSON object at the top level")
            observations.append(
                observation(
                    prefix, f"Fresh {name}", "pass", "sha256:" + hashlib.sha256(content).hexdigest()
                )
            )
        except FileNotFoundError:
            for n, check in enumerate(checks, 1):
                observations.append(
                    observation(f"{prefix}.{n}", check["field"], "skipped", "Artifact missing")
                )
            continue
        except (DoctorError, OSError, UnicodeError) as exc:
            # A missing/invalid file is an observed failure; unreadable/oversize evidence is unknown.
            limited = isinstance(exc, OSError) or "limit" in str(exc) or "regular file" in str(exc)
            observations.append(
                observation(prefix, f"Fresh {name}", "unknown" if limited else "fail", str(exc))
            )
            for n, check in enumerate(checks, 1):
                observations.append(
                    observation(
                        f"{prefix}.{n}",
                        check["field"],
                        "skipped",
                        "Artifact could not be validated",
                    )
                )
            continue
        for n, check in enumerate(checks, 1):
            field = check["field"]
            ok = field in data
            if ok and "type" in check:
                ok = matches_type(data[field], check["type"])
            if ok and check.get("nonempty"):
                ok = isinstance(data[field], (str, list, dict)) and len(data[field]) > 0
            if ok and "equals" in check:
                ok = equal_json(data[field], check["equals"])
            observations.append(
                observation(
                    f"{prefix}.{n}",
                    f"{name}: {field}",
                    "pass" if ok else "fail",
                    "Declared assertion satisfied" if ok else "Declared assertion not satisfied",
                )
            )
    return observations
