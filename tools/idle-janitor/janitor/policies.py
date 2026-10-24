"""Policy engine — declarative rules the janitor and the AI agent respect.

Policies live at ~/.idle-janitor/policies.yaml. If the file is missing we fall
back to a conservative built-in default (nothing is auto-reaped; postgres is
protected).

Schema (YAML):

    protect:                       # never reap, never recommend reaping
      - image_contains: postgres
      - image_contains: mysql
      - name_contains: production
    rules:
      - name: reap-stale-ngrok
        match:
          kind: process
          name_contains: ngrok
          idle_minutes_min: 60
        action: reap
      - name: warn-stale-vite
        match:
          kind: process
          name_contains: vite
          idle_minutes_min: 180
        action: warn

Supported match keys: kind, name_contains, image_contains, cmdline_contains,
idle_minutes_min, cpu_percent_max.
Supported actions: reap | warn | snooze (snooze_minutes extra key).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

POLICIES_FILE = Path.home() / ".idle-janitor" / "policies.yaml"

DEFAULT_POLICIES: dict[str, Any] = {
    "protect": [
        {"image_contains": "postgres"},
        {"image_contains": "mysql"},
        {"image_contains": "mariadb"},
        {"name_contains": "production"},
        {"name_contains": "prod-"},
    ],
    "rules": [
        {
            "name": "reap-stale-ngrok",
            "match": {"kind": "process", "name_contains": "ngrok", "idle_minutes_min": 60},
            "action": "reap",
        },
        {
            "name": "warn-stale-vite",
            "match": {"kind": "process", "name_contains": "vite", "idle_minutes_min": 180},
            "action": "warn",
        },
        {
            "name": "warn-very-old-containers",
            "match": {"kind": "docker", "idle_minutes_min": 1440},  # 24h
            "action": "warn",
        },
    ],
}


@dataclass
class Decision:
    """A single policy decision about a single resource."""

    resource_id: str
    name: str
    kind: str
    rule: str
    action: str  # reap | warn | protect | snooze | none
    reason: str
    snooze_minutes: int | None = None


def load_policies() -> dict[str, Any]:
    if not POLICIES_FILE.exists():
        return DEFAULT_POLICIES
    try:
        data = yaml.safe_load(POLICIES_FILE.read_text()) or {}
    except (yaml.YAMLError, OSError):
        return DEFAULT_POLICIES
    # Merge with defaults so new keys fall back cleanly.
    merged = {**DEFAULT_POLICIES, **data}
    return merged


def write_default_policies(force: bool = False) -> Path:
    """Materialize the default policies file so the user can tweak it."""
    if POLICIES_FILE.exists() and not force:
        return POLICIES_FILE
    POLICIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    POLICIES_FILE.write_text(yaml.safe_dump(DEFAULT_POLICIES, sort_keys=False))
    return POLICIES_FILE


def _match_resource(match: dict[str, Any], resource: dict[str, Any]) -> bool:
    if "kind" in match and resource.get("kind") != match["kind"]:
        return False
    if "name_contains" in match:
        if match["name_contains"].lower() not in (resource.get("name", "") or "").lower():
            return False
    if "image_contains" in match:
        if match["image_contains"].lower() not in (resource.get("image", "") or "").lower():
            return False
    if "cmdline_contains" in match:
        if match["cmdline_contains"].lower() not in (resource.get("cmdline", "") or "").lower():
            return False
    if "idle_minutes_min" in match:
        if int(resource.get("uptime_seconds", 0)) / 60 < float(match["idle_minutes_min"]):
            return False
        if not resource.get("idle", False):
            return False
    if "cpu_percent_max" in match:
        if float(resource.get("cpu_percent", 0.0)) > float(match["cpu_percent_max"]):
            return False
    return True


def _is_protected(resource: dict[str, Any], protect: list[dict[str, Any]]) -> bool:
    return any(_match_resource(p, resource) for p in protect)


def evaluate(
    resources: list[dict[str, Any]], policies: dict[str, Any] | None = None
) -> list[Decision]:
    """Run every policy rule against every resource. One Decision per hit.

    Order: protect rules win (short-circuit); then first matching rule in order.
    """
    policies = policies or load_policies()
    protect = policies.get("protect") or []
    rules = policies.get("rules") or []

    decisions: list[Decision] = []
    for resource in resources:
        if _is_protected(resource, protect):
            decisions.append(
                Decision(
                    resource_id=resource.get("id", ""),
                    name=resource.get("name", ""),
                    kind=resource.get("kind", ""),
                    rule="protect",
                    action="protect",
                    reason="matched a protect clause",
                )
            )
            continue

        for rule in rules:
            match = rule.get("match") or {}
            if not _match_resource(match, resource):
                continue
            action = (rule.get("action") or "warn").lower()
            snooze_minutes = rule.get("snooze_minutes") if action == "snooze" else None
            decisions.append(
                Decision(
                    resource_id=resource.get("id", ""),
                    name=resource.get("name", ""),
                    kind=resource.get("kind", ""),
                    rule=rule.get("name", "unnamed-rule"),
                    action=action,
                    reason=_reason_for(rule, resource),
                    snooze_minutes=snooze_minutes,
                )
            )
            break  # first-match wins per resource

    return decisions


def _reason_for(rule: dict[str, Any], resource: dict[str, Any]) -> str:
    match = rule.get("match") or {}
    bits = []
    if "idle_minutes_min" in match:
        mins = int(resource.get("uptime_seconds", 0)) / 60
        bits.append(f"idle for {mins:.0f}m \u2265 {match['idle_minutes_min']}m")
    if "name_contains" in match:
        bits.append(f"name matches '{match['name_contains']}'")
    if "image_contains" in match:
        bits.append(f"image matches '{match['image_contains']}'")
    if "cpu_percent_max" in match:
        bits.append(
            f"cpu {resource.get('cpu_percent', 0):.1f}% \u2264 {match['cpu_percent_max']}%"
        )
    return "; ".join(bits) or "matched rule"


def decisions_to_dicts(decisions: list[Decision]) -> list[dict[str, Any]]:
    return [
        {
            "resource_id": d.resource_id,
            "name": d.name,
            "kind": d.kind,
            "rule": d.rule,
            "action": d.action,
            "reason": d.reason,
            "snooze_minutes": d.snooze_minutes,
        }
        for d in decisions
    ]
