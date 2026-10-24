from __future__ import annotations

import re
import shlex
from pathlib import Path
from urllib.parse import unquote, urlsplit

from claimcheck.ledger import Claim, Result
from claimcheck.safety import project_file
from claimcheck.sandbox import SANDBOX_IMAGE, run_command


def discover(text: str, source: str = "README.md") -> list[Claim]:
    claims: list[Claim] = []
    in_shell = False
    fence = False
    last_command: Claim | None = None
    for line, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if stripped.startswith("```"):
            fence = not fence
            in_shell = fence and stripped[3:].strip() in {"sh", "bash", "shell", "console"}
            last_command = None
            continue
        if in_shell:
            if stripped.startswith("# expect:") and last_command is not None:
                last_command.data["expected"] = stripped.split(":", 1)[1].strip()
            elif stripped and not stripped.startswith("#"):
                command = stripped.removeprefix("$ ")
                last_command = Claim.create(
                    "readme.command", source, line, command, command=command
                )
                claims.append(last_command)
        elif not fence:
            for match in re.finditer(r"(?<!!)\[[^\]]+\]\(([^)\s]+)\)", raw):
                target = match.group(1)
                if not urlsplit(target).scheme and not target.startswith(("#", "//")):
                    claims.append(
                        Claim.create(
                            "readme.link",
                            source,
                            line,
                            f"Local link exists: {target}",
                            target=target,
                        )
                    )
    return claims


def check(claim: Claim, root: Path, *, allow_exec: bool, image: str = SANDBOX_IMAGE) -> Result:
    if claim.kind == "readme.link":
        target = unquote(urlsplit(claim.data["target"]).path)
        path = project_file(root, target)
        exists = path.exists()
        return Result(
            claim.id,
            "passed" if exists else "failed",
            f"Link target {'exists' if exists else 'is missing'}: {target}",
            {"path": target},
        )
    command = claim.data["command"]
    if not allow_exec:
        return Result(
            claim.id,
            "not_verified",
            "Command execution disabled; enable --allow-exec for a trusted project.",
        )
    # No shell: operators, expansion, redirection and multi-line scripts stay unverified.
    if any(char in command for char in "|;&><$`\\\n") or command.startswith(("cd ", "export ")):
        return Result(claim.id, "not_verified", "Requires shell/stateful execution; not supported.")
    argv = shlex.split(command)
    result = run_command(root, argv, image=image)
    evidence = {
        "argv": argv,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "timed_out": result.timed_out,
        "sandbox_image": image,
    }
    if result.timed_out or result.returncode in {125, 126, 127}:
        return Result(claim.id, "error", "Sandbox could not complete this check.", evidence)
    if result.returncode:
        return Result(claim.id, "failed", "Documented command exited unsuccessfully.", evidence)
    expected = claim.data.get("expected")
    if expected and expected not in result.stdout:
        return Result(
            claim.id, "failed", f"Expected stdout substring is absent: {expected}", evidence
        )
    return Result(
        claim.id,
        "passed",
        "Command exited successfully" + (" and expected stdout matched." if expected else "."),
        evidence,
    )
