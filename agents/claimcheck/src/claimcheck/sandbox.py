from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

SANDBOX_IMAGE = "python@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704"
OUTPUT_LIMIT = 16_384
SNAPSHOT_LIMIT = 20 * 1024 * 1024
EXCLUDED = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "reports",
    "credentials.json",
    "service-account.json",
    "id_rsa",
    "id_ed25519",
}


@dataclass(frozen=True)
class Execution:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def execute(argv: list[str], *, timeout: float = 20) -> Execution:
    """Bound captured output and kill the process group on timeout (POSIX)."""
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        process = subprocess.Popen(
            argv, stdout=out, stderr=err, stdin=subprocess.DEVNULL, start_new_session=True
        )
        timed_out = False
        try:
            deadline = time.monotonic() + timeout
            while process.poll() is None:
                if os.fstat(out.fileno()).st_size > OUTPUT_LIMIT:
                    raise OverflowError("stdout output limit exceeded")
                if os.fstat(err.fileno()).st_size > OUTPUT_LIMIT:
                    raise OverflowError("stderr output limit exceeded")
                if time.monotonic() > deadline:
                    raise subprocess.TimeoutExpired(argv, timeout)
                time.sleep(0.02)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        except OverflowError as exc:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            return Execution(125, "", str(exc))
        out.seek(0)
        err.seek(0)
        stdout = out.read(OUTPUT_LIMIT + 1)
        stderr = err.read(OUTPUT_LIMIT + 1)
        if len(stdout) > OUTPUT_LIMIT or len(stderr) > OUTPUT_LIMIT:
            return Execution(125, "", "Output limit exceeded", timed_out)
        return Execution(
            process.returncode,
            stdout.decode(errors="replace"),
            stderr.decode(errors="replace"),
            timed_out,
        )


def snapshot(root: Path, destination: Path) -> None:
    """Exclude common secret files and symlinks; do not expose the original project mount."""
    total = count = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [
            name
            for name in dirs
            if name not in EXCLUDED
            and not name.startswith(".")
            and not (Path(directory) / name).is_symlink()
        ]
        for name in files:
            path = Path(directory) / name
            if (
                path.is_symlink()
                or name.startswith(".")
                or name in EXCLUDED
                or path.suffix.lower() in {".pem", ".key", ".crt", ".cer", ".der", ".p12", ".pfx"}
                or "credential" in name.lower()
                or name.startswith("service-account")
            ):
                continue
            if not path.is_file():
                continue
            total += path.stat().st_size
            count += 1
            if total > SNAPSHOT_LIMIT or count > 1000:
                raise ValueError("Sandbox snapshot exceeds 20 MiB or 1000 files")
            target = destination / path.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            target.chmod(0o755 if os.access(path, os.X_OK) else 0o644)


def run_command(root: Path, argv: list[str], *, image: str = SANDBOX_IMAGE) -> Execution:
    with tempfile.TemporaryDirectory(prefix="claimcheck-snapshot-") as directory:
        copied = Path(directory)
        # The unprivileged container user must be able to traverse this snapshot.
        copied.chmod(0o755)
        snapshot(root, copied)
        return _run_snapshot(copied, argv, image=image)


def _run_snapshot(root: Path, argv: list[str], *, image: str) -> Execution:
    if not argv or argv[0].startswith("-"):
        raise ValueError("Command must name an executable")
    if "," in str(root):
        raise ValueError("Docker mount paths containing commas are unsupported")
    name = f"claimcheck-{uuid.uuid4().hex}"
    command = [
        "docker",
        "run",
        "--rm",
        "--pull=never",
        "--name",
        name,
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=64",
        "--memory=256m",
        "--cpus=1",
        "--user=65534:65534",
        "--tmpfs=/tmp:rw,noexec,nosuid,size=16m",
        "--mount",
        f"type=bind,src={root.resolve()},dst=/project,readonly",
        "--workdir=/project",
        "--env=HOME=/tmp",
        "--env=PYTHONDONTWRITEBYTECODE=1",
        "--entrypoint",
        argv[0],
        image,
        *argv[1:],
    ]
    try:
        return execute(command)
    finally:
        # A killed Docker client does not necessarily stop its container.
        cleanup = execute(["docker", "rm", "--force", name], timeout=10)
        if cleanup.returncode and "No such container" not in cleanup.stderr:
            raise RuntimeError(f"Sandbox cleanup failed: {cleanup.stderr.strip()}")
