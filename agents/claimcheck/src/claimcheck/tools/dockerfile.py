from __future__ import annotations

import json
import re
import shlex
from typing import Any

from claimcheck.ledger import Claim, Result
from claimcheck.sandbox import execute


def discover(text: str, source: str = "Dockerfile") -> list[Claim]:
    claims: list[Claim] = []
    # Only final-stage configuration is comparable to the final image.
    instructions: dict[str, tuple[int, str]] = {}
    ports: dict[str, None] = {}
    env: dict[str, str] = {}
    stage = 0
    for line, raw in enumerate(text.splitlines(), 1):
        match = re.match(r"^\s*([A-Za-z]+)\s+(.*?)\s*$", raw)
        if not match:
            continue
        instruction, value = match.group(1).upper(), match.group(2)
        if instruction == "FROM":
            stage += 1
            instructions.clear()
            ports.clear()
            env.clear()
        elif instruction == "EXPOSE":
            ports.update(
                dict.fromkeys(port if "/" in port else port + "/tcp" for port in value.split())
            )
            instructions[instruction] = (line, value)
        elif instruction == "ENV":
            pairs = shlex.split(value)
            if not pairs or any("=" not in pair for pair in pairs):
                claims.append(
                    Claim.create(
                        "unsupported", source, line, "Legacy ENV syntax needs manual comparison."
                    )
                )
                continue
            for pair in pairs:
                key, val = pair.split("=", 1)
                env[key] = val
            instructions[instruction] = (line, value)
        elif instruction in {"USER", "WORKDIR", "CMD", "ENTRYPOINT"}:
            instructions[instruction] = (line, value)
    for instruction, (line, value) in instructions.items():
        expected: Any = value
        if instruction in {"CMD", "ENTRYPOINT"}:
            if not value.startswith("["):
                claims.append(
                    Claim.create(
                        "unsupported",
                        source,
                        line,
                        f"{instruction} uses shell form; manual comparison required.",
                    )
                )
                continue
            expected = json.loads(value)
            if not isinstance(expected, list) or not all(
                isinstance(argument, str) for argument in expected
            ):
                raise ValueError(f"{instruction} must be a JSON array of strings")
        elif instruction == "EXPOSE":
            expected = sorted(ports)
        elif instruction == "ENV":
            expected = env
        claims.append(
            Claim.create(
                "docker.config",
                source,
                line,
                f"Image matches {instruction} {value}",
                instruction=instruction,
                expected=expected,
                stages=stage,
            )
        )
    return claims


def inspect_image(image: str) -> dict[str, Any]:
    if not image or image.startswith("-"):
        raise ValueError("Image must be a non-option Docker image reference")
    result = execute(["docker", "image", "inspect", image], timeout=15)
    if result.returncode:
        raise RuntimeError(f"Cannot inspect image: {result.stderr.strip()}")
    images = json.loads(result.stdout)
    if len(images) != 1:
        raise ValueError("Expected exactly one Docker image")
    image_data: dict[str, Any] = images[0]
    return image_data


def check(claim: Claim, image_data: dict[str, Any]) -> Result:
    instruction = claim.data["instruction"]
    config = image_data["Config"]
    fields = {"USER": "User", "WORKDIR": "WorkingDir", "CMD": "Cmd", "ENTRYPOINT": "Entrypoint"}
    expected = claim.data["expected"]
    if instruction == "EXPOSE":
        observed: Any = sorted(config.get("ExposedPorts") or {})
        matches = all(port in observed for port in expected)
    elif instruction == "ENV":
        observed = dict(pair.split("=", 1) for pair in config.get("Env", []) if "=" in pair)
        # Never export unrelated image environment values (which may contain secrets).
        observed = {key: observed.get(key) for key in expected}
        matches = observed == expected
    else:
        observed = config.get(fields[instruction])
        matches = observed == expected
    if "$" in str(expected) or "\\" in str(expected) or claim.data.get("stages", 1) > 1:
        return Result(
            claim.id,
            "not_verified",
            "Build substitutions, continuations, or multiple stages require manual comparison.",
        )
    return Result(
        claim.id,
        "passed" if matches else "failed",
        f"{instruction}: expected {expected!r}; image has {observed!r}",
        {"image_id": image_data["Id"], "expected": expected, "actual": observed},
    )
