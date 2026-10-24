from __future__ import annotations

import contextlib
import json
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

from claimcheck.sandbox import execute


def fixture_root() -> Path:
    source = Path(__file__).resolve().parents[2] / "fixtures" / "lying-notes"
    packaged = Path(__file__).resolve().parent / "fixtures" / "lying-notes"
    root = source if source.is_dir() else packaged
    if not root.is_dir():
        raise FileNotFoundError("Bundled lying-notes fixture is missing")
    return root


@contextlib.contextmanager
def demo_server() -> Iterator[str]:
    """Execute only our bundled synthetic fixture, never a selected project's server."""
    with tempfile.TemporaryDirectory(prefix="claimcheck-demo-") as directory:
        ready = Path(directory) / "ready.json"
        with tempfile.TemporaryFile() as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(fixture_root() / "app.py"),
                    "--port",
                    "0",
                    "--ready-file",
                    str(ready),
                ],
                stdout=log,
                stderr=log,
                env={"PYTHONDONTWRITEBYTECODE": "1"},
            )
            try:
                deadline = time.monotonic() + 10
                while not ready.exists():
                    if process.poll() is not None or time.monotonic() > deadline:
                        log.seek(0)
                        raise RuntimeError(f"Demo server failed to start: {log.read(4096)!r}")
                    time.sleep(0.05)
                port = json.loads(ready.read_text())["port"]
                yield f"http://127.0.0.1:{port}"
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


@contextlib.contextmanager
def demo_image(enabled: bool) -> Iterator[str | None]:
    if not enabled:
        yield None
        return
    name = "claimcheck-demo:" + uuid.uuid4().hex
    try:
        result = execute(
            [
                "docker",
                "build",
                "--pull=false",
                "--network=none",
                "--tag",
                name,
                "--file",
                str(fixture_root() / "Dockerfile.image"),
                str(fixture_root()),
            ],
            timeout=120,
        )
        if result.returncode:
            raise RuntimeError(f"Demo image build failed: {result.stderr}")
        yield name
    finally:
        cleanup = execute(["docker", "image", "rm", name])
        if cleanup.returncode and "No such image" not in cleanup.stderr:
            raise RuntimeError(f"Demo image cleanup failed: {cleanup.stderr}")
