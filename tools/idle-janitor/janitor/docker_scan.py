"""Scan running Docker containers and detect idle ones.

Idle heuristic (v1): CPU% averaged over a short sample window is below a
threshold. We also surface uptime and memory so the AI agent (and the human)
can make an informed call.

Everything degrades gracefully if the Docker daemon isn't running — we return
an empty list with an error string so the MCP tool stays usable on machines
without Docker.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from . import cost

try:
    import docker  # type: ignore
    from docker.errors import DockerException  # type: ignore
except ImportError:  # pragma: no cover
    docker = None  # type: ignore
    DockerException = Exception  # type: ignore


def _client():
    if docker is None:
        raise RuntimeError(
            "The `docker` Python package is not installed. Run `pip install docker`."
        )
    return docker.from_env()


def _cpu_percent(stats: dict[str, Any]) -> float:
    """Approximate CPU% from a single `docker stats` sample.

    Mirrors the formula the `docker stats` CLI uses.
    """
    try:
        cpu_stats = stats["cpu_stats"]
        precpu_stats = stats["precpu_stats"]
        cpu_delta = (
            cpu_stats["cpu_usage"]["total_usage"]
            - precpu_stats["cpu_usage"]["total_usage"]
        )
        system_delta = (
            cpu_stats.get("system_cpu_usage", 0)
            - precpu_stats.get("system_cpu_usage", 0)
        )
        online_cpus = cpu_stats.get("online_cpus") or len(
            cpu_stats["cpu_usage"].get("percpu_usage") or [1]
        )
        if system_delta > 0 and cpu_delta > 0:
            return (cpu_delta / system_delta) * online_cpus * 100.0
    except (KeyError, TypeError, ZeroDivisionError):
        pass
    return 0.0


def _uptime_seconds(started_at: str) -> float:
    # Docker returns RFC3339 with nanoseconds; trim to microseconds.
    if "." in started_at:
        head, tail = started_at.split(".", 1)
        tz_split = max(tail.find("+"), tail.find("Z"))
        if tz_split == -1:
            tz_split = len(tail)
        frac = tail[:tz_split][:6]
        suffix = tail[tz_split:].replace("Z", "+00:00")
        started_at = f"{head}.{frac}{suffix}"
    else:
        started_at = started_at.replace("Z", "+00:00")
    try:
        started = datetime.fromisoformat(started_at)
    except ValueError:
        return 0.0
    now = datetime.now(timezone.utc)
    return max(0.0, (now - started).total_seconds())


def list_containers(idle_cpu_threshold: float = 1.0) -> dict[str, Any]:
    """Return every running container with idleness + cost context.

    Returns a dict so the MCP tool response is self-describing even when empty
    or errored.
    """
    try:
        client = _client()
        client.ping()
    except (DockerException, RuntimeError) as exc:
        return {
            "ok": False,
            "error": f"Docker not reachable: {exc}",
            "containers": [],
        }

    results: list[dict[str, Any]] = []
    for container in client.containers.list():
        try:
            stats = container.stats(stream=False)
            cpu_pct = _cpu_percent(stats)
            mem_bytes = (stats.get("memory_stats") or {}).get("usage", 0) or 0
        except DockerException:
            cpu_pct = 0.0
            mem_bytes = 0

        started_at = container.attrs.get("State", {}).get("StartedAt", "")
        uptime = _uptime_seconds(started_at)
        image_name = ""
        try:
            tags = container.image.tags or []
            image_name = tags[0] if tags else container.image.short_id
        except DockerException:
            image_name = container.attrs.get("Config", {}).get("Image", "unknown")

        watts = cost.estimate_watts("docker", image_name)
        wh = cost.wh_from(watts, uptime)
        inr = cost.inr_from(wh)
        co2_g = cost.co2_g_from(wh)

        results.append(
            {
                "id": f"docker:{container.short_id}",
                "name": container.name,
                "image": image_name,
                "uptime_seconds": int(uptime),
                "uptime_human": _human_time(uptime),
                "cpu_percent": round(cpu_pct, 2),
                "mem_mb": round(mem_bytes / (1024 * 1024), 1),
                "idle": cpu_pct < idle_cpu_threshold,
                "estimated_watts": watts,
                "wh": round(wh, 2),
                "inr": round(inr, 2),
                "co2_g": round(co2_g, 2),
                "kind": "docker",
            }
        )

    return {"ok": True, "containers": results}


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


def terminate(container_short_id: str, dry_run: bool = False) -> dict[str, Any]:
    """Stop a container by its short ID. Dry run returns what would happen."""
    try:
        client = _client()
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}

    try:
        container = client.containers.get(container_short_id)
    except DockerException as exc:
        return {"ok": False, "error": f"Container not found: {exc}"}

    plan = {
        "id": f"docker:{container.short_id}",
        "name": container.name,
        "image": container.attrs.get("Config", {}).get("Image", "unknown"),
    }
    if dry_run:
        return {"ok": True, "dry_run": True, "would_terminate": plan}

    try:
        container.stop(timeout=10)
    except DockerException as exc:
        return {"ok": False, "error": f"Failed to stop container: {exc}", "plan": plan}
    return {"ok": True, "terminated": plan}
