"""Fresh-clone install test inside a locked-down Docker container.

Untrusted PR code is never run on the host, and never runs with network access:

  phase 1, "fetch" (network on): download dependencies only, without executing
           anything from the PR. Python: `pip download --only-binary=:all:`
           (wheels only, so no setup.py runs). Node: `npm ci --ignore-scripts`.
  phase 2, "verify" (--network=none, --user 65534, --read-only, caps dropped):
           install from the downloaded files and compile / build offline.

If Docker is missing, the step is skipped and the report says so. It is never
silently counted as passed.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from .models import Criterion, Finding, Severity, Submission

TIMEOUT = 300  # seconds per phase
HARDENING = ["--rm", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--memory=1g", "--cpus=1",
             "--pids-limit=256"]
OFFLINE = ["--network=none", "--user", "65534:65534", "--read-only", "--tmpfs", "/tmp:rw,exec,size=512m"]
PY_IMAGE, NODE_IMAGE = "python:3.12-slim", "node:20-slim"


def available() -> bool:
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode == 0


def plan(proj: Path, work: Path) -> tuple[Optional[str], list[tuple[str, list[str]]]]:
    """(skip_reason, [(phase, docker argv)]). Pure function, so it is unit-testable without Docker.

    `proj` is mounted read-only. `work` is a host scratch folder that phase 1
    fills (wheels / node_modules) and phase 2 reads.
    """
    if (proj / "package.json").exists():
        fetch = ["docker", "run", *HARDENING, "--tmpfs", "/tmp:rw,size=256m",
                 "-v", f"{proj}:/src:ro", "-v", f"{work}:/out", NODE_IMAGE, "sh", "-c",
                 "set -e; cp -r /src/. /out/app && cd /out/app && "
                 "if [ -f package-lock.json ]; then npm ci --ignore-scripts --no-audit --no-fund; "
                 "else npm install --ignore-scripts --no-audit --no-fund; fi"]
        verify = ["docker", "run", *HARDENING, *OFFLINE, "-e", "HOME=/tmp", "-e", "npm_config_cache=/tmp/npm",
                  "-v", f"{work}:/out", "-w", "/out/app", NODE_IMAGE, "sh", "-c",
                  "set -e; npm run build --if-present --offline; echo GATEKEEPER_OK"]
        return None, [("fetch", fetch), ("verify", verify)]
    if (proj / "requirements.txt").exists():
        fetch = ["docker", "run", *HARDENING, "--tmpfs", "/tmp:rw,size=256m",
                 "-v", f"{proj}:/src:ro", "-v", f"{work}:/wheels", PY_IMAGE, "sh", "-c",
                 "pip download -q --disable-pip-version-check --only-binary=:all: -d /wheels -r /src/requirements.txt"]
        verify = ["docker", "run", *HARDENING, *OFFLINE, "-e", "HOME=/tmp", "-e", "PYTHONDONTWRITEBYTECODE=1",
                  "-v", f"{proj}:/src:ro", "-v", f"{work}:/wheels:ro", PY_IMAGE, "sh", "-c",
                  "set -e; pip install -q --disable-pip-version-check --no-index --find-links /wheels "
                  "--target /tmp/site -r /src/requirements.txt && "
                  # syntax-check every file in memory (the source mount is read-only, nothing is written)
                  "python -c \"import pathlib; [compile(p.read_bytes(), str(p), 'exec') "
                  "for p in pathlib.Path('/src').rglob('*.py') if '/.' not in str(p)]\" && "
                  "echo GATEKEEPER_OK"]
        return None, [("fetch", fetch), ("verify", verify)]
    if (proj / "pyproject.toml").exists():
        return ("pyproject.toml-only projects are not install-tested: building them would run the PR's build "
                "backend. Add a requirements.txt to enable the sandboxed test."), []
    return "no supported manifest (requirements.txt or package.json)", []


def run(sub: Submission) -> tuple[dict, list[Finding]]:
    proj = sub.project_path
    if not proj or not proj.is_dir():
        return {"status": "skipped", "reason": "no project folder"}, []
    if not available():
        return {"status": "skipped", "reason": "Docker not available"}, [Finding(
            "sandbox.skipped", Severity.INFO, Criterion.REPRODUCIBILITY,
            "Fresh-install test was skipped (Docker not available). Setup was only checked statically.",
        )]
    work = Path(tempfile.mkdtemp(prefix="gatekeeper-sandbox-"))
    try:
        reason, phases = plan(proj, work)
        if reason:
            return {"status": "skipped", "reason": reason}, [Finding(
                "sandbox.skipped", Severity.INFO, Criterion.REPRODUCIBILITY, f"Fresh-install test skipped: {reason}")]
        t0, log, ok = time.time(), "", True
        for phase, cmd in phases:
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
                log += f"[{phase}] " + (r.stdout + r.stderr)[-1500:]
                ok = r.returncode == 0 and (phase != "verify" or "GATEKEEPER_OK" in r.stdout)
            except subprocess.TimeoutExpired:
                log += f"[{phase}] timed out after {TIMEOUT}s"
                ok = False
            if not ok:
                break
    finally:
        shutil.rmtree(work, ignore_errors=True)
    image = PY_IMAGE if "python" in " ".join(phases[0][1]) else NODE_IMAGE
    info = {"status": "passed" if ok else "failed", "image": image, "seconds": round(time.time() - t0),
            "log_tail": log[-3000:], "network_during_verify": False}
    if ok:
        return info, [Finding("sandbox.passed", Severity.INFO, Criterion.REPRODUCIBILITY,
                              f"Dependencies installed and code compiled offline in a fresh `{image}` "
                              f"container ({info['seconds']}s).")]
    return info, [Finding(
        "sandbox.failed", Severity.MAJOR, Criterion.REPRODUCIBILITY,
        f"Fresh install failed in `{image}`. Last output:\n```\n{log[-800:]}\n```",
        fix="Reproduce in a clean venv/container and pin missing or conflicting dependencies. Note: only prebuilt "
            "wheels are allowed, so packages that need building from source must be pinned to a version with wheels.",
    )]
