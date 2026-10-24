"""Social collectors via official public APIs only. Items are always "unconfirmed" and can
never block a commit on their own.

- Mastodon: public hashtag timelines (no auth).
- Bluesky: public AppView author feeds for an allowlist of accounts (no auth).
- X/Twitter: API v2 recent search; disabled unless a paid bearer token is configured.
"""

from __future__ import annotations

import os
from typing import Any

from rce_sentinel.intel.base import Collector, make_item
from rce_sentinel.models import Dependency, IntelItem


class Mastodon(Collector):
    name = "mastodon"
    confirmed = False

    def get(self, inventory: list[Dependency]) -> Any:
        base = self.cfg.get("instance", "https://infosec.exchange").rstrip("/")
        out = []
        for tag in self.cfg.get("hashtags", []):
            out += self.http.get_json(f"{base}/api/v1/timelines/tag/{tag}",
                                      params={"limit": 40})
        return out

    def parse(self, raw: Any) -> list[IntelItem]:
        return [make_item(self.name, s.get("url") or s.get("uri", ""),
                          f"@{(s.get('account') or {}).get('acct', '?')}", s.get("content", ""),
                          self.credibility, confirmed=False,
                          published=s.get("created_at", ""))
                for s in raw or []]


class Bluesky(Collector):
    name = "bluesky"
    confirmed = False
    API = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"

    def get(self, inventory: list[Dependency]) -> Any:
        out = []
        for actor in self.cfg.get("actors", []):
            out += self.http.get_json(self.API, params={"actor": actor, "limit": 30}).get(
                "feed", [])
        return out

    def parse(self, raw: Any) -> list[IntelItem]:
        items = []
        for entry in raw or []:
            post = entry.get("post", {})
            handle = (post.get("author") or {}).get("handle", "")
            rkey = post.get("uri", "").rsplit("/", 1)[-1]
            items.append(make_item(self.name, f"https://bsky.app/profile/{handle}/post/{rkey}",
                                   f"@{handle}", (post.get("record") or {}).get("text", ""),
                                   self.credibility, confirmed=False,
                                   published=post.get("indexedAt", "")))
        return items


class XTwitter(Collector):
    name = "x_twitter"
    confirmed = False
    API = "https://api.x.com/2/tweets/search/recent"

    def enabled(self) -> bool:
        return super().enabled() and bool(os.environ.get(self.cfg.get("token_env", "")))

    def get(self, inventory: list[Dependency]) -> Any:
        token = os.environ[self.cfg["token_env"]]
        return self.http.get_json(self.API, headers={"Authorization": f"Bearer {token}"},
                                  params={"query": self.cfg["query"], "max_results": 50,
                                          "tweet.fields": "created_at"})

    def parse(self, raw: Any) -> list[IntelItem]:
        return [make_item(self.name, f"https://x.com/i/web/status/{t['id']}", "post",
                          t.get("text", ""), self.credibility, confirmed=False,
                          published=t.get("created_at", ""))
                for t in (raw or {}).get("data", [])]
