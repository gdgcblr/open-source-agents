"""Firebase local-emulator adapter.

Firebase's emulator suite (`firebase emulators:start`) spawns a hub process
that listens on localhost:4400 and exposes GET /emulators returning JSON like:

    {
      "functions": {"name": "functions", "host": "localhost", "port": 5001, "pid": 12345},
      "firestore": {"name": "firestore", "host": "localhost", "port": 8080, "pid": 12345},
      ...
    }

This module probes the hub (never phones home \u2014 strictly 127.0.0.1), returns a
clean list, and estimates the running cost per emulator. If the hub isn't
reachable (Firebase CLI not installed, emulators not running), we return an
empty "ok" response so callers can degrade gracefully.

We also expose a `patterns()` helper so the process scanner can surface the
parent Firebase CLI process in `idle-janitor status` even without the hub.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from . import cost

HUB_URL = "http://127.0.0.1:4400/emulators"
HUB_TIMEOUT_S = 1.0

# Rough idle-draw per emulator type (JVM-heavy ones are 3-5x node-based).
_EMULATOR_WATTS: dict[str, float] = {
    "firestore": 15.0,
    "database": 12.0,
    "pubsub": 8.0,
    "storage": 10.0,
    "functions": 8.0,
    "auth": 5.0,
    "hosting": 3.0,
    "eventarc": 5.0,
    "extensions": 5.0,
    "tasks": 5.0,
    "ui": 4.0,
    "hub": 2.0,
}

# Pattern tokens the main process scanner should also look for so firebase
# emulators show up in generic listings even if the hub probe fails.
FIREBASE_PATTERNS: list[str] = [
    r"firebase emulators:start",
    r"firebase-tools/lib/emulator",
]


def _emulator_watts(name: str) -> float:
    return _EMULATOR_WATTS.get((name or "").lower(), 6.0)


def _probe_hub() -> dict[str, Any] | None:
    """Return the hub JSON if reachable, else None."""
    req = Request(HUB_URL, headers={"User-Agent": "idle-janitor/0.1"})
    try:
        with urlopen(req, timeout=HUB_TIMEOUT_S) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError, ConnectionError, OSError):
        return None


def list_emulators() -> dict[str, Any]:
    """Return every running Firebase emulator we can see via the hub.

    Uptime is unknown (the hub doesn't tell us when each emulator started), so
    cost estimates use a conservative 'started an hour ago' assumption with a
    note in the response.
    """
    data = _probe_hub()
    if data is None:
        return {
            "ok": False,
            "error": (
                "Firebase emulator hub not reachable at 127.0.0.1:4400. "
                "Start it with `firebase emulators:start` or install firebase-tools."
            ),
            "emulators": [],
        }

    emulators: list[dict[str, Any]] = []
    # Assume 1h uptime for cost math unless we can find a better source.
    assumed_uptime_s = 3600
    for key, meta in (data or {}).items():
        if not isinstance(meta, dict):
            continue
        name = meta.get("name") or key
        watts = _emulator_watts(name)
        wh = cost.wh_from(watts, assumed_uptime_s)
        inr = cost.inr_from(wh)
        co2_g = cost.co2_g_from(wh)
        emulators.append(
            {
                "id": f"firebase:{name}",
                "name": name,
                "kind": "firebase",
                "host": meta.get("host"),
                "port": meta.get("port"),
                "pid": meta.get("pid"),
                "estimated_watts": watts,
                "assumed_uptime_seconds": assumed_uptime_s,
                "wh": round(wh, 2),
                "inr": round(inr, 2),
                "co2_g": round(co2_g, 2),
                "idle": True,  # emulators are always idle unless actively test-driven
            }
        )

    return {
        "ok": True,
        "emulator_count": len(emulators),
        "emulators": emulators,
        "note": (
            "Uptime per emulator isn't exposed by the hub; cost math uses a "
            "conservative 1h assumption. Reap by stopping the parent "
            "`firebase emulators:start` process or running `firebase emulators:stop`."
        ),
    }


def patterns() -> list[str]:
    """Expose Firebase-specific cmdline patterns to the main process scanner."""
    return list(FIREBASE_PATTERNS)
