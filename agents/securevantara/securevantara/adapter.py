"""Bounded POSIX subprocess adapter. No arbitrary flags or dynamic targets."""
import hashlib
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import stat
import subprocess
import time

VERSION = "4.6.159"


def execute(command, timeout=30, limit=65536):
    """Drain both pipes, retaining at most limit bytes per stream."""
    if not math.isfinite(timeout) or not 0 < timeout <= 3600:
        raise ValueError("timeout must be finite and in (0, 3600]")
    if type(limit) is not int or not 1 <= limit <= 1048576:
        raise ValueError("output limit must be 1..1048576 bytes per stream")
    result = dict(command=command, exit_status=None, error=None,
                  timed_out=False, truncated=False, stdout="", stderr="")
    env = {k: v for k, v in os.environ.items()
           if k in {"PATH", "HOME", "TMPDIR", "LANG", "SSL_CERT_FILE"}
           or k in {"XALGORIX_LLM", "XALGORIX_LLM_PROVIDER",
                    "XALGORIX_API_KEY", "XALGORIX_API_BASE",
                    "XALGORIX_MAX_ITERATIONS"}}
    env.update(XALGORIX_NO_AUTO_UPDATE="1", XALGORIX_ALLOW_AUTO_INSTALL="false",
               XALGORIX_AUTO_INSTALL_SUDO="false")
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    process = None
    try:
        with selectors.DefaultSelector() as selector:
            process = subprocess.Popen(command, shell=False, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       start_new_session=True, env=env)
            for name in buffers:
                stream = getattr(process, name)
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            deadline = time.monotonic() + timeout
            while selector.get_map() or process.poll() is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    result.update(timed_out=True, error="execution timeout")
                    break
                for key, _ in selector.select(min(remaining, 0.1)):
                    data = os.read(key.fileobj.fileno(), 8192)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    buf = buffers[key.data]
                    capacity = limit - len(buf)
                    buf.extend(data[:capacity])
                    if len(data) > capacity:
                        result["truncated"] = True
            if result["timed_out"]:
                _kill(process)
            result["exit_status"] = process.wait(timeout=1)
            if result["exit_status"] and not result["error"]:
                result["error"] = "non-zero exit status"
    except (OSError, subprocess.SubprocessError) as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
    finally:
        if process is not None:
            if process.poll() is None:
                _kill(process)
            try:
                result["exit_status"] = process.wait(timeout=1)
            except subprocess.SubprocessError:
                result["error"] = "process could not be reaped"
            for name in buffers:
                stream = getattr(process, name)
                if stream:
                    stream.close()
        for name, buf in buffers.items():
            result[name] = bytes(buf).decode("utf-8", errors="replace")
    return result


def _kill(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def authorize(source, scope, authorized):
    if authorized is not True:
        raise ValueError("explicit source-review authorization required")
    if not source or not scope:
        raise ValueError("source and scope are required")
    root = Path(source).resolve(strict=True)
    allowed = Path(scope).resolve(strict=True)
    if not root.is_dir() or root != allowed:
        raise ValueError("scope must equal the canonical source directory")
    def walk_error(error):
        raise error

    # A symlink can make an otherwise local tree reference data outside scope.
    for parent, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        if any((Path(parent) / name).is_symlink() for name in dirs + files):
            raise ValueError("source tree contains symlinks; use an isolated snapshot")
        if any(not stat.S_ISREG((Path(parent) / name).stat().st_mode) for name in files):
            raise ValueError("source contains special files; use a regular-file snapshot")
    return root


def run_xalgorix(executable="xalgorix", source=None, scope=None,
                  authorized=False, sandboxed=False, timeout=300, limit=65536):
    """Probe a pinned binary, optionally review an authorized local snapshot."""
    root = None
    if source is not None:
        root = authorize(source, scope, authorized)
        if sandboxed is not True:
            raise ValueError("external sandbox acknowledgement required")
    resolved = shutil.which(executable)
    if resolved is None:
        return {"error": "Xalgorix executable not found", "runs": []}
    digest = hashlib.sha256(Path(resolved).read_bytes()).hexdigest()
    probe = execute([resolved, "--version"], min(timeout, 30), limit)
    report = dict(binary_sha256=digest, expected_version=VERSION, runs=[probe],
                  findings=[], normalization="unsupported CLI text; raw evidence only",
                  error=probe["error"])
    if probe["error"]:
        return report
    if not re.search(r"(?m)^xalgorix v" + re.escape(VERSION) + r"\s*$", probe["stdout"]):
        report["error"] = "unsupported or malformed Xalgorix version output"
        return report
    if root is not None:
        run = execute([resolved, "--source", str(root), "--code-scan", "review"],
                      timeout, limit)
        report["runs"].append(run)
        report["error"] = run["error"]
    return report
