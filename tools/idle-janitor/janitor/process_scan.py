"""Scan running local dev-server processes (node, vite, next, uvicorn, ngrok, ...).

Intentionally conservative:
  * Patterns are matched as whole words (regex \\b boundaries), not substrings,
    so `serve` won't match macOS `SystemUIServer`.
  * Processes whose executable lives under a system path (/System, /usr/libexec,
    /Library/..., /sbin, ...) are skipped entirely — those are never dev servers.
  * A hard blocklist of known system/user-application process names acts as a
    second safety net.
"""

from __future__ import annotations

import re
import time
from typing import Any

import psutil

from . import cost

# Patterns matched as whole words against the full command line. Each pattern
# is wrapped in \b...\b and matched case-insensitively.
DEV_SERVER_PATTERNS: list[str] = [
    r"next dev",
    r"next start",
    r"\bvite\b",
    r"webpack serve",
    r"webpack-dev-server",
    r"\bnodemon\b",
    r"ng serve",
    r"react-scripts start",
    r"nuxt dev",
    r"astro dev",
    r"remix dev",
    r"\buvicorn\b",
    r"\bgunicorn\b",
    r"flask run",
    r"manage\.py runserver",
    r"rails server\b",
    r"\brails s\b",
    r"jekyll serve",
    r"hugo server",
    r"\bngrok\b",
    r"cloudflared tunnel",
    r"\blocaltunnel\b",
    r"\blive-server\b",
    r"\bhttp-server\b",
    r"\bnpx serve\b",
    r"\byarn serve\b",
    r"\bpnpm serve\b",
    r"ollama serve",
    r"firebase emulators:start",
    r"firebase-tools/lib/emulator",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in DEV_SERVER_PATTERNS]


def _pattern_slug(pattern: str) -> str:
    """Convert a regex pattern like r'\\bngrok\\b' or 'next dev' into a display slug."""
    slug = re.sub(r"\\b", "", pattern)
    slug = re.sub(r"\\", "", slug)
    return slug.strip()


_COMPILED_WITH_SLUG = list(zip([_pattern_slug(p) for p in DEV_SERVER_PATTERNS], _COMPILED))

# Executables under these path prefixes are never considered dev servers.
# NOTE: we deliberately do NOT exclude /opt/homebrew/Cellar/ or /Applications/
# \u2014 real `ollama`, `node`, `uvicorn`, etc. live there. The BLOCKLIST_NAMES
# basename check is our main safety net; the path prefixes below are reserved
# for things an end-user would never knowingly spawn as a dev server.
SYSTEM_PATH_PREFIXES: tuple[str, ...] = (
    "/System/",
    "/usr/libexec/",
    "/usr/sbin/",
    "/sbin/",
    "/Library/Apple/",
    "/Library/PrivilegedHelperTools/",
    "/Library/CoreMediaIO/",
)

# Process-name blocklist (basename). Belt and suspenders.
BLOCKLIST_NAMES: frozenset[str] = frozenset(
    {
        # init / system
        "systemd",
        "launchd",
        "init",
        "kernel_task",
        # macOS UI daemons we never touch
        "WindowServer",
        "SystemUIServer",
        "AccessibilityUIServer",
        "ContinuityCaptureAgent",
        "donotdisturbd",
        "coreaudiod",
        "loginwindow",
        "mds",
        "mds_stores",
        "Finder",
        "Dock",
        # IDEs / editors / shells the user is likely actively using
        "Cursor",
        "Cursor Helper",
        "Code",
        "Code Helper",
        "zsh",
        "bash",
        "fish",
        "ssh",
        "sshd",
        # Browsers
        "Google Chrome",
        "Google Chrome Helper",
        "firefox",
        "Safari",
    }
)


def _cmdline(proc: psutil.Process) -> str:
    try:
        return " ".join(proc.cmdline())
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return ""


def _exe(proc: psutil.Process) -> str:
    try:
        return proc.exe() or ""
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return ""


def _is_dev_server(cmdline: str) -> bool:
    return any(rx.search(cmdline) for rx in _COMPILED)


def _matched_slug(cmdline: str) -> str | None:
    """Return the first dev-server pattern that matches, as a human-friendly slug."""
    for slug, rx in _COMPILED_WITH_SLUG:
        if rx.search(cmdline):
            return slug.split()[0]  # first word of the slug
    return None


def _is_system(exe_path: str, name: str) -> bool:
    if name in BLOCKLIST_NAMES:
        return True
    if any(exe_path.startswith(p) for p in SYSTEM_PATH_PREFIXES):
        return True
    return False


def _human_time(seconds: float) -> str:
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if mins and not days:
        parts.append(f"{mins}m")
    return " ".join(parts) or "<1m"


def list_processes(idle_cpu_threshold: float = 1.0) -> dict[str, Any]:
    """List running local dev servers with idleness + cost context."""
    candidates: list[psutil.Process] = []

    for proc in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            name = proc.info.get("name") or ""
            exe_path = _exe(proc)
            if _is_system(exe_path, name):
                continue
            cmdline = _cmdline(proc)
            if not cmdline or not _is_dev_server(cmdline):
                continue
            proc.cpu_percent(interval=None)  # prime sampler
            candidates.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if candidates:
        time.sleep(0.4)  # give cpu_percent a sampling window

    results: list[dict[str, Any]] = []
    now = time.time()
    for proc in candidates:
        try:
            cmdline = _cmdline(proc)
            if not cmdline:
                continue
            cpu_pct = proc.cpu_percent(interval=None)
            try:
                mem_bytes = proc.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                mem_bytes = 0
            uptime = max(0.0, now - proc.create_time())
            # Display name: the dev-server pattern that matched (e.g., "ngrok",
            # "vite") beats the executable name (e.g., "Python") every time.
            name = _matched_slug(cmdline) or proc.name() or "process"
            watts = cost.estimate_watts("process", cmdline or name)
            wh = cost.wh_from(watts, uptime)
            inr = cost.inr_from(wh)
            co2_g = cost.co2_g_from(wh)

            results.append(
                {
                    "id": f"proc:{proc.pid}",
                    "pid": proc.pid,
                    "name": name,
                    "cmdline": cmdline[:200],
                    "uptime_seconds": int(uptime),
                    "uptime_human": _human_time(uptime),
                    "cpu_percent": round(cpu_pct, 2),
                    "mem_mb": round(mem_bytes / (1024 * 1024), 1),
                    "idle": cpu_pct < idle_cpu_threshold,
                    "estimated_watts": watts,
                    "wh": round(wh, 2),
                    "inr": round(inr, 2),
                    "co2_g": round(co2_g, 2),
                    "kind": "process",
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return {"ok": True, "processes": results}


def terminate(pid: int, dry_run: bool = False, force: bool = False) -> dict[str, Any]:
    """Kill a dev-server process by PID.

    Safety: we re-check the cmdline against DEV_SERVER_PATTERNS and the
    system blocklist before killing. A stale ID can never be weaponized to
    terminate a system process.
    """
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return {"ok": False, "error": f"No such process: {pid}"}

    try:
        cmdline = _cmdline(proc)
        name = proc.name()
        exe_path = _exe(proc)
    except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
        return {"ok": False, "error": f"Cannot inspect process: {exc}"}

    if _is_system(exe_path, name) or not _is_dev_server(cmdline):
        return {
            "ok": False,
            "error": "Refusing to terminate: process is not on the dev-server allowlist.",
            "pid": pid,
            "name": name,
            "cmdline": cmdline[:200],
        }

    plan = {"id": f"proc:{pid}", "pid": pid, "name": name, "cmdline": cmdline[:200]}
    if dry_run:
        return {"ok": True, "dry_run": True, "would_terminate": plan}

    try:
        if force:
            proc.kill()
        else:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except psutil.TimeoutExpired:
                proc.kill()
    except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
        return {"ok": False, "error": f"Failed to terminate: {exc}", "plan": plan}

    return {"ok": True, "terminated": plan}
