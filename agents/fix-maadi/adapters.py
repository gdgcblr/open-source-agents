"""Safe handoff contracts for Fix Maadi channels.

Adapters prepare an action for a human to review. They intentionally do not
submit complaints, bypass authentication, or solve CAPTCHA challenges.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HandoffAction:
    mode: str
    label: str
    destination: str | None
    requires_user_confirmation: bool = True


class ChannelAdapter:
    mode = "base"

    def prepare(self, channel: dict[str, Any], case: dict[str, Any]) -> HandoffAction:
        raise NotImplementedError


class CopyTextAdapter(ChannelAdapter):
    mode = "copy_text"

    def prepare(self, channel: dict[str, Any], case: dict[str, Any]) -> HandoffAction:
        return HandoffAction(self.mode, "Copy prepared complaint", None)


class ExternalLinkAdapter(ChannelAdapter):
    def prepare(self, channel: dict[str, Any], case: dict[str, Any]) -> HandoffAction:
        destination = channel.get("destination") or channel.get("source")
        label = {"whatsapp_handoff": "Open WhatsApp", "phone_handoff": "Open phone dialler"}.get(self.mode, "Open official service")
        return HandoffAction(self.mode, label, destination)


ADAPTERS = {
    "copy_text": CopyTextAdapter(),
    "portal_handoff": ExternalLinkAdapter(),
    "guided_handoff": ExternalLinkAdapter(),
    "whatsapp_handoff": ExternalLinkAdapter(),
    "phone_handoff": ExternalLinkAdapter(),
}


def prepare_handoff(channel: dict[str, Any], case: dict[str, Any]) -> HandoffAction:
    """Return a reviewable action; fail closed for unknown modes."""
    adapter = ADAPTERS.get(channel.get("mode"), CopyTextAdapter())
    return adapter.prepare(channel, case)
