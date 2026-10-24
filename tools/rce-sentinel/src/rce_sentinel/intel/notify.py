"""Webhook notifications (Slack or Discord). Messages carry ids and links only."""

from __future__ import annotations

import os

from rce_sentinel.netio import BlockedHost, SafeClient


def notify(http: SafeClient, text: str) -> list[str]:
    sent = []
    for env, key in (("SLACK_WEBHOOK_URL", "text"), ("DISCORD_WEBHOOK_URL", "content")):
        url = os.environ.get(env)
        if not url:
            continue
        try:
            http.post_json(url, {key: text[:1800]})
            sent.append(env)
        except (BlockedHost, Exception) as exc:  # notification failure must not stop the loop
            sent.append(f"{env} failed: {type(exc).__name__}")
    return sent
