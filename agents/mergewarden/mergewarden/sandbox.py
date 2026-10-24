"""Fresh-clone install test inside a locked-down Docker container.

Untrusted PR code is never run on the host. If Docker is missing, the step
is skipped and the report says so. It is never silently counted as passed.
"""

from __future__ import annotations

import shutil
import subprocess
import time

from .models import Criterion, Finding, Severity, Submission

TIMEOUT = 300
PY_SCRIPT = r"""
set -e
cp -r /src /work && cd /work
if [ -f requirements.txt ]; then pip install -q --disable-pip-version-check -r requirements.txt
elif [ -f pyproject.toml ]; then pip install -q --disable-pip-version-check .
fi
python -m compileall -q . > /dev/null
echo "GATEKEEPER_OK"
"""
NODE_SCRIPT = r"""
set -e
cp -r /src /work && cd /work
if [ -f package-lock.json ]; then npm ci --ignore-scripts --no-audit --no-fund; else npm install --ignore-scripts --no-audit --no-fund; fi
npm run build --if-present
echo "GATEKEEPER_OK"
"""


def available() -> bool:
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode == 0


def run(sub: Submission) -> tuple[dict, list[Finding]]:
    proj = sub.project_path
    if not proj or not proj.is_dir():
        return {"status": "skipped", "reason": "no project folder"}, []
    if not available():
        return {"status": "skipped", "reason": "Docker not available"}, [Finding(
            "sandbox.skipped", Severity.INFO, Criterion.REPRODUCIBILITY,
            "Fresh-install test was skipped (Docker not available). Setup was only checked statically.",
        )]
    if (proj / "package.json").exists():
        image, script = "node:20-slim", NODE_SCRIPT
    elif any((proj / f).exists() for f in ("requirements.txt", "pyproject.toml")):
        image, script = "python:3.12-slim", PY_SCRIPT
    else:
        return {"status": "skipped", "reason": "no supported manifest"}, []
    cmd = [
        "docker", "run", "--rm", "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--memory=1g", "--cpus=1", "--pids-limit=256", "--tmpfs", "/tmp:rw,size=256m",
        "-v", f"{proj}:/src:ro", image, "sh", "-c", script,
    ]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
        log, ok = (r.stdout + r.stderr)[-3000:], "GATEKEEPER_OK" in r.stdout
    except subprocess.TimeoutExpired:
        log, ok = f"timed out after {TIMEOUT}s", False
    info = {"status": "passed" if ok else "failed", "image": image, "seconds": round(time.time() - t0), "log_tail": log}
    if ok:
        return info, [Finding("sandbox.passed", Severity.INFO, Criterion.REPRODUCIBILITY,
                              f"Dependencies installed cleanly in a fresh `{image}` container ({info['seconds']}s).")]
    return info, [Finding(
        "sandbox.failed", Severity.MAJOR, Criterion.REPRODUCIBILITY,
        f"Fresh install failed in `{image}`. Last output:\n```\n{log[-800:]}\n```",
        fix="Reproduce in a clean venv/container and pin missing or conflicting dependencies.",
    )]
