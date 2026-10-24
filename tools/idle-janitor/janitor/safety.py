"""Central safety / guardrail module.

Every destructive code path in idle-janitor \u2014 the MCP terminate_resource and
apply_policies tools, the CLI `reap` and `agent` commands \u2014 goes through
`check_reap()` before touching anything. The design goal is defense in depth:
even if the policy engine, the process-scan allowlist, or the client all have
bugs, this module is the final gate.

Layers enforced here:
    1. Hard blocklist      \u2014 process names/paths we must never touch
                             (launchd, WindowServer, Cursor, /System/..., ...)
    2. Pattern allowlist   \u2014 for processes, cmdline must match a known
                             dev-server pattern
    3. Policy protect      \u2014 anything matching a `protect:` clause in
                             ~/.idle-janitor/policies.yaml is immutable
    4. Snooze              \u2014 user said "leave this alone", we leave it alone
    5. Rate limit          \u2014 at most N reaps in a rolling window to stop
                             runaway agent loops

A fifth-but-silent layer is also here: cmdline redaction for log output, so a
leaked API key never ends up in SQLite or in our returned error messages.
"""

from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import psutil

from . import policies as policies_mod
from . import process_scan, snooze as snooze_store


# -- Rate limiter ------------------------------------------------------------

@dataclass
class _RateLimiter:
    max_actions: int = 10
    window_seconds: float = 60.0
    _hits: deque[float] = field(default_factory=deque)

    def allow(self) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        while self._hits and self._hits[0] < cutoff:
            self._hits.popleft()
        if len(self._hits) >= self.max_actions:
            return False, 0
        return True, self.max_actions - len(self._hits) - 1

    def record(self) -> None:
        self._hits.append(time.monotonic())


_rate_limiter = _RateLimiter()


def configure_rate_limit(max_actions: int = 10, window_seconds: float = 60.0) -> None:
    """Tune the global rate limiter. Mostly for tests + CLI flags."""
    global _rate_limiter
    _rate_limiter = _RateLimiter(max_actions=max_actions, window_seconds=window_seconds)


# -- Secret redaction --------------------------------------------------------

_SECRETISH_FLAGS = re.compile(
    # --flag=value  or  --flag value  (0, 1, or 2 leading dashes)
    r"(-{0,2}(?:token|password|passwd|secret|api[-_]?key|auth|authorization|bearer|session)[=\s]+)([^\s\"']+)",
    re.IGNORECASE,
)
_HEADER_AUTH = re.compile(
    # Authorization: Bearer <value>  or  Authorization: Basic <value>
    r"(authorization:\s*(?:bearer|basic|token)\s+)([^\s\"'<>]+)",
    re.IGNORECASE,
)
_URL_WITH_CREDS = re.compile(
    # scheme://user:password@host  for ANY scheme (mysql, postgres, redis, http, ...)
    r"([a-zA-Z][a-zA-Z0-9+\-.]*://)([^:/@\s]+):([^@\s]+)(@)",
    re.IGNORECASE,
)


def redact(text: str) -> str:
    """Mask likely-sensitive values in a cmdline / log line."""
    if not text:
        return text
    text = _URL_WITH_CREDS.sub(
        lambda m: m.group(1) + m.group(2) + ":***REDACTED***" + m.group(4), text
    )
    text = _HEADER_AUTH.sub(lambda m: m.group(1) + "***REDACTED***", text)
    text = _SECRETISH_FLAGS.sub(lambda m: m.group(1) + "***REDACTED***", text)
    return text


# -- Core guard --------------------------------------------------------------

@dataclass
class Verdict:
    allowed: bool
    reasons: list[str]
    rate_limit_remaining: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reasons": self.reasons,
            "rate_limit_remaining": self.rate_limit_remaining,
        }


def _resource_for_id(resource_id: str) -> dict[str, Any] | None:
    """Try to resolve a resource dict from an id, for policy evaluation.

    For processes we build a minimal dict from psutil live so we can check
    protect clauses even if the resource wasn't in the latest scan.
    """
    if not resource_id or ":" not in resource_id:
        return None
    kind, _, raw = resource_id.partition(":")
    if kind == "proc":
        try:
            pid = int(raw)
            proc = psutil.Process(pid)
            cmdline = " ".join(proc.cmdline())
            name = process_scan._matched_slug(cmdline) or proc.name() or "process"
            return {
                "id": resource_id,
                "kind": "process",
                "name": name,
                "cmdline": cmdline,
                "uptime_seconds": int(max(0, time.time() - proc.create_time())),
                "idle": True,
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
            return None
    if kind == "docker":
        try:
            from . import docker_scan
            client = docker_scan._client()
            container = client.containers.get(raw)
            return {
                "id": resource_id,
                "kind": "docker",
                "name": container.name,
                "image": container.attrs.get("Config", {}).get("Image", ""),
                "uptime_seconds": 0,
                "idle": True,
            }
        except Exception:  # noqa: BLE001  \u2014 degrade gracefully
            return None
    return None


def check_reap(resource_id: str, resource: dict[str, Any] | None = None) -> Verdict:
    """The one authoritative "may I terminate this?" gate.

    Returns a Verdict. Callers must respect it. If allowed=True, callers must
    call `record_action()` immediately before the destructive syscall so the
    rate limiter stays consistent.
    """
    reasons: list[str] = []
    if not resource_id or ":" not in resource_id:
        return Verdict(
            allowed=False,
            reasons=["resource_id must look like 'docker:<id>' or 'proc:<pid>'"],
        )

    kind, _, raw = resource_id.partition(":")

    # Resolve a resource dict if the caller didn't give us one.
    if resource is None:
        resource = _resource_for_id(resource_id) or {}

    # --- Layer 1: snooze -----------------------------------------------------
    if snooze_store.is_snoozed(resource_id):
        reasons.append("resource is snoozed by the user")
        return Verdict(allowed=False, reasons=reasons)

    # --- Layer 2: hard blocklist / pattern allowlist (processes only) -------
    # NOTE: the resource-id prefix is "proc" (short), while the resource-dict
    # kind field is "process" (long). We check against "proc" here because
    # that's what partition() yields from the id.
    if kind == "proc":
        try:
            pid = int(raw)
        except ValueError:
            return Verdict(allowed=False, reasons=[f"invalid pid: {raw!r}"])
        try:
            proc = psutil.Process(pid)
            name = proc.name()
        except psutil.NoSuchProcess:
            return Verdict(allowed=False, reasons=[f"no such process: {pid}"])
        except psutil.AccessDenied:
            # If we can't even see the process name, we're definitely not
            # allowed to touch it.
            reasons.append(f"access denied inspecting pid {pid} \u2014 not a process we own")
            return Verdict(allowed=False, reasons=reasons)

        # cmdline() and exe() can each independently raise AccessDenied on
        # system processes even when name() succeeds; treat either failure as
        # "system / not ours".
        try:
            cmdline = " ".join(proc.cmdline())
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            cmdline = ""
        try:
            exe = proc.exe()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            exe = ""

        if process_scan._is_system(exe, name):
            reasons.append(
                f"process is on the system blocklist (name={name!r}, exe={exe!r})"
            )
            return Verdict(allowed=False, reasons=reasons)
        # If cmdline is empty (common for system processes we can't fully
        # inspect), refuse. We never try to kill something we can't name.
        if not cmdline:
            reasons.append(
                f"process cmdline unreadable (pid={pid}, name={name!r}) \u2014 refusing"
            )
            return Verdict(allowed=False, reasons=reasons)
        if not process_scan._is_dev_server(cmdline):
            reasons.append(
                "process cmdline doesn't match any dev-server pattern on the allowlist"
            )
            return Verdict(allowed=False, reasons=reasons)

    # --- Layer 3: policy protect clauses ------------------------------------
    if resource:
        policies = policies_mod.load_policies()
        protect_clauses = policies.get("protect") or []
        for clause in protect_clauses:
            if policies_mod._match_resource(clause, resource):
                reasons.append(
                    f"resource matches a policy protect clause: {clause}"
                )
                return Verdict(allowed=False, reasons=reasons)

    # --- Layer 4: rate limit (reserve a slot but don't consume yet) ---------
    allowed_by_rate, remaining = _rate_limiter.allow()
    if not allowed_by_rate:
        reasons.append(
            f"rate limit: already {_rate_limiter.max_actions} reaps in the last "
            f"{int(_rate_limiter.window_seconds)}s; cooling off"
        )
        return Verdict(allowed=False, reasons=reasons, rate_limit_remaining=0)

    return Verdict(allowed=True, reasons=["ok"], rate_limit_remaining=remaining)


def record_action() -> None:
    """Record that a destructive action is about to happen. Call this
    immediately before the kill/stop syscall so the rate limiter is tight."""
    _rate_limiter.record()
