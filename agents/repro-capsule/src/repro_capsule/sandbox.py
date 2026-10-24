"""Fixed-command Docker sandbox for Python unittest discovery."""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import Thread

IMAGE = "python:3.12-slim"
TEST_COMMAND = ("python", "-m", "unittest", "discover", "-v")
TIMEOUT_SECONDS = 120
OUTPUT_LIMIT = 16_000


@dataclass(frozen=True)
class TestResult:
    status: str
    exit_code: int | None
    stdout: str
    stderr: str
    command: tuple[str, ...] = TEST_COMMAND
    image: str | None = IMAGE


class SandboxError(RuntimeError):
    """Raised when the requested isolated run cannot be started safely."""


def docker_command(repo: Path, *, container_name: str | None = None) -> list[str]:
    """Build the only command the agent is permitted to run in the repository."""
    docker_bin = os.environ.get("REPRO_CAPSULE_DOCKER_BIN", "docker")
    container_name = container_name or f"repro-capsule-{uuid.uuid4().hex}"
    return [
        docker_bin, "run", "--rm", "--name", container_name, "--pull=never",
        "--network=none", "--read-only",
        "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=64",
        "--memory=512m", "--cpus=1", "--user=65534:65534",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "--mount", f"type=bind,source={repo},target=/workspace,readonly",
        "--workdir=/workspace", "--env=PYTHONDONTWRITEBYTECODE=1", IMAGE, *TEST_COMMAND,
    ]


def _drain_bounded(stream, output: list[str]) -> None:
    """Drain a child pipe fully while retaining only its final bounded output."""
    captured = bytearray()
    while chunk := stream.read(8192):
        captured.extend(chunk)
        if len(captured) > OUTPUT_LIMIT:
            del captured[:len(captured) - OUTPUT_LIMIT]
    output.append(captured.decode("utf-8", errors="replace"))


def run_tests(repo: Path, *, allow_execution: bool) -> TestResult:
    """Run fixed unittest discovery; execution is opt-in and confined by Docker."""
    resolved = repo.resolve(strict=True)
    if not resolved.is_dir():
        raise SandboxError("Repository path must be a directory.")
    if not allow_execution:
        return TestResult("blocked", None, "", "Execution requires --allow-execution.")
    docker_bin = os.environ.get("REPRO_CAPSULE_DOCKER_BIN", "docker")
    if docker_bin == "docker" and not shutil.which(docker_bin):
        raise SandboxError("Docker CLI not found. Install Docker and pre-pull python:3.12-slim.")
    container_name = f"repro-capsule-{uuid.uuid4().hex}"
    try:
        process = subprocess.Popen(
            docker_command(resolved, container_name=container_name),
            cwd=os.fspath(resolved), shell=False,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise SandboxError(f"Could not start Docker: {exc}") from exc
    stdout: list[str] = []
    stderr: list[str] = []
    readers = [
        Thread(target=_drain_bounded, args=(process.stdout, stdout), daemon=True),
        Thread(target=_drain_bounded, args=(process.stderr, stderr), daemon=True),
    ]
    for reader in readers:
        reader.start()
    timed_out = False
    try:
        process.wait(timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            subprocess.run(
                [docker_bin, "stop", "--time", "1", container_name],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=10, shell=False, check=False,
            )
            process.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
            process.wait()
    for reader in readers:
        reader.join()
    return TestResult(
        "timeout" if timed_out else "passed" if process.returncode == 0 else "failed",
        None if timed_out else process.returncode, stdout[0], stderr[0],
    )
