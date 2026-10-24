from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class ArmorScreenResult:
    blocked: bool
    reason: str | None
    service_available: bool


def model_armor_configured() -> bool:
    return bool(
        os.environ.get("MODEL_ARMOR_PROJECT_ID")
        and os.environ.get("MODEL_ARMOR_TEMPLATE_ID")
    )


def screen_text(text: str, *, direction: str = "input") -> ArmorScreenResult:
    """
    Optional Google Cloud Model Armor integration.

    When not configured, returns service_available=False and does not block.
    Local deterministic guardrails remain mandatory.
    """
    if not model_armor_configured():
        return ArmorScreenResult(blocked=False, reason=None, service_available=False)

    # Placeholder hook: wire google.cloud.modelarmor_v1 when credentials exist.
    # Avoid importing GCP client in unit tests / offline environments.
    return ArmorScreenResult(
        blocked=False,
        reason=None,
        service_available=True,
    )
