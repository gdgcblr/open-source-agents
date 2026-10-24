"""Trusted-code execution with fresh files, bounded capture, and POSIX cleanup.

A working copy is not a sandbox. The target still runs as the current OS user.
"""

import hashlib
import os
import selectors
import signal
import stat
import subprocess
import time
from pathlib import Path

from .contract import DoctorError, contained_file

MAX_COPY_BYTES = 20 * 1024 * 1024
MAX_FILES = 1000
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_LOG_BYTES = 65536
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".doctor-reports",
    "dist",
    "build",
}


def excluded(name):
    return (
        name in SKIP_DIRS
        or name.endswith(".egg-info")
        or name == ".env"
        or name.startswith(".env.")
        and name != ".env.example"
        or name.endswith((".key", ".pem", ".pyc"))
        or name in {"credentials.json", "secrets.json", "id_rsa", "id_ed25519"}
        or name.startswith("service-account")
    )


def copy_project(root, destination, contract):
    """Copy bounded regular inputs; declared outputs are never copied."""
    digest = hashlib.sha256()
    count = total = 0
    outputs = {a["path"] for a in contract.artifacts}
    for path in sorted(outputs):
        existing = contained_file(root, path)
        if existing.exists() and not existing.is_file():
            raise DoctorError(f"Artifact must be a file, not a directory: {path}")
    for parent, dirs, files in os.walk(root, followlinks=False):
        dirs.sort()
        files.sort()
        keep = []
        for name in dirs:
            source = Path(parent) / name
            if excluded(name):
                continue
            if source.is_symlink():
                raise DoctorError(f"Source directory symlink is unsupported: {name}")
            keep.append(name)
        dirs[:] = keep
        for name in files:
            if excluded(name):
                continue
            source = Path(parent) / name
            relative = source.relative_to(root).as_posix()
            if relative in outputs:
                continue
            contained_file(root, relative)
            if not stat.S_ISREG(source.stat().st_mode):
                raise DoctorError(f"Only regular source files are supported: {relative}")
            count += 1
            if count > MAX_FILES:
                raise DoctorError(f"Project exceeds {MAX_FILES} copied files")
            with source.open("rb") as stream:
                content = stream.read(MAX_FILE_BYTES + 1)
            total += len(content)
            if len(content) > MAX_FILE_BYTES or total > MAX_COPY_BYTES:
                raise DoctorError("Project exceeds the source-copy byte limit")
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            digest.update(relative.encode() + b"\x00" + content + b"\x00")
    return {"sha256": digest.hexdigest(), "copied_files": count, "copied_bytes": total}


def resolve_python(value):
    if not Path(value).is_absolute():
        raise DoctorError("--python must be an absolute executable path")
    executable = str(Path(value).absolute())
    if not Path(executable).is_file() or not os.access(executable, os.X_OK):
        raise DoctorError("Selected Python executable is unavailable")
    return executable


def child_environment(environment, names, home):
    result = {
        "PATH": os.defpath,
        "HOME": str(home),
        "TMPDIR": str(home),
        "LANG": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
    }
    result.update({name: environment[name] for name in names if environment.get(name)})
    return result


def _kill_group(pid):
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run_process(command, cwd, environment, timeout, redactor):
    if os.name != "posix":
        raise DoctorError("v0.1 execution supports macOS/Linux (POSIX) only")
    started = time.monotonic()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    truncated = {"stdout": False, "stderr": False}
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        shell=False,
    )
    status = "completed"
    with selectors.DefaultSelector() as selector:
        for name in buffers:
            stream = getattr(process, name)
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        try:
            while selector.get_map() or process.poll() is None:
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    status = "timed_out"
                    break
                for key, _ in selector.select(min(remaining, 0.05)):
                    chunk = os.read(key.fileobj.fileno(), 8192)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    name = key.data
                    room = MAX_LOG_BYTES - len(buffers[name])
                    buffers[name].extend(chunk[:room])
                    truncated[name] |= len(chunk) > room
        finally:
            # Kill descendants even when the direct child already exited.
            _kill_group(process.pid)
            process.wait()
            process.stdout.close()
            process.stderr.close()
    return {
        "status": status,
        "returncode": process.returncode,
        "duration_seconds": round(time.monotonic() - started, 6),
        **{name: redactor.log(bytes(data), truncated[name]) for name, data in buffers.items()},
        "logs_truncated": any(truncated.values()),
    }
