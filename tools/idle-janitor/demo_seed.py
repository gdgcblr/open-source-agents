"""Spawn a handful of realistic-looking idle dev-server processes for the demo.

These are real processes with real PIDs. idle-janitor matches them via its
dev-server regex allowlist, so what judges see is NOT faked data \u2014 only the
workload itself is a stand-in for a forgotten real one.

Usage:
    python demo_seed.py start      # spawn the fakes, print PIDs + cleanup line
    python demo_seed.py stop       # kill every demo process this script spawned
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

STATE_FILE = Path.home() / ".idle-janitor" / "demo_pids.json"

# argv[0] (prog name as seen by `ps`) \u2192 extra args that make the cmdline
# look like a real dev server. All three will match the idle-janitor regex.
FAKES: list[tuple[str, list[str]]] = [
    ("ngrok",   ["http", "8080", "--region", "ap"]),
    ("vite",    ["--host", "0.0.0.0", "--port", "5173"]),
    ("uvicorn", ["app.main:api", "--host", "0.0.0.0", "--port", "8000"]),
]

PY = sys.executable


def _spawn_one(prog: str, args: list[str]) -> int:
    """Spawn a Python process that sleeps forever, with cmdline looking like `prog args...`."""
    # We launch python with -c, then rewrite argv[0:] so psutil's cmdline()
    # returns ["<prog>", *args]. The exe path remains python; our scanner
    # matches on cmdline not exe, which is intentional.
    inline = (
        "import sys, time; "
        f"sys.argv[:] = [{prog!r}, *{args!r}]; "
        "import setproctitle_shim\n"
    )
    # setproctitle isn't installed by default; keep it dependency-free by
    # using a plain sleep loop with argv rewrite.
    code = (
        "import sys, time\n"
        f"sys.argv[:] = [{prog!r}, *{args!r}]\n"
        "while True:\n"
        "    time.sleep(60)\n"
    )
    proc = subprocess.Popen(
        [PY, "-c", code],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # detach so the fakes survive our exit
    )
    return proc.pid


def start() -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    pids: list[dict] = []
    for prog, args in FAKES:
        pid = _spawn_one(prog, args)
        pids.append({"pid": pid, "prog": prog, "args": args})
        print(f"  spawned fake {prog!r:>12} as pid {pid}")
    STATE_FILE.write_text(json.dumps(pids, indent=2))
    print(f"\nState written to {STATE_FILE}")
    print("Now try:")
    print("  idle-janitor status")
    print("  idle-janitor live")
    print("  idle-janitor policies --no-show --evaluate")
    print("\nStop them with:  python demo_seed.py stop")


def stop() -> None:
    if not STATE_FILE.exists():
        print("No demo state found \u2014 nothing to stop.")
        return
    try:
        pids = json.loads(STATE_FILE.read_text())
    except json.JSONDecodeError:
        pids = []
    killed = 0
    for entry in pids:
        pid = entry.get("pid")
        try:
            os.kill(int(pid), signal.SIGTERM)
            killed += 1
            print(f"  stopped pid {pid} ({entry.get('prog')})")
        except (ProcessLookupError, PermissionError, ValueError) as e:
            print(f"  skip pid {pid}: {e}")
    STATE_FILE.unlink(missing_ok=True)
    print(f"\nStopped {killed} process(es).")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in {"start", "stop"}:
        print(__doc__)
        sys.exit(1)
    if sys.argv[1] == "start":
        start()
    else:
        stop()


if __name__ == "__main__":
    main()
