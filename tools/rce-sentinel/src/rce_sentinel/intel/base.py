"""Collector interface and sanitisation for untrusted intel text.

Collectors only emit metadata: ids, links, titles, short prose summaries, package names.
Code blocks, command lines, and encoded blobs are stripped before anything is stored, so
exploit payloads never land in the database or in a prompt.
"""

from __future__ import annotations

import hashlib
import html
import re
from abc import ABC, abstractmethod
from typing import Any

from rce_sentinel.models import Dependency, IntelItem
from rce_sentinel.netio import SafeClient

CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b")
CWE_RE = re.compile(r"\bCWE-\d{1,4}\b")
_BLOCKS = re.compile(r"<(pre|code|script|style)\b.*?</\1>|```.*?```", re.S | re.I)
_TAGS = re.compile(r"<[^>]+>")
_PAYLOAD_LINE = re.compile(
    r"^\s*(\$ |#!|curl |wget |python3? -c|powershell|bash -c|nc |ncat |echo .*\|)|"
    r"[A-Za-z0-9+/=]{80,}|\\x[0-9a-f]{2}(\\x[0-9a-f]{2}){7,}",
    re.I | re.M,
)
_INLINE_CODE = re.compile(r"`[^`]{40,}`")
_INLINE_CMD = re.compile(
    r"\b(?:curl|wget)\s+\S+(?:\s*\|\s*\S+)*"
    r"|\b(?:bash|sh|zsh|python3?|powershell|nc|ncat|perl|ruby)\s+-[A-Za-z]+\s+\S+"
    r"|\|\s*(?:ba|z)?sh\b|!!python/\S+|\$\{jndi:[^}]*\}|\b(?:os\.system|subprocess\.\w+|eval|exec)\s*\([^)]*\)",
    re.I,
)


def strip_payloads(text: str, limit: int = 600) -> str:
    """Prose-only summary: no code blocks, command lines, or long encoded strings."""
    text = _BLOCKS.sub(" ", text or "")
    text = _TAGS.sub(" ", text)
    text = html.unescape(text)
    text = "\n".join(ln for ln in text.splitlines() if not _PAYLOAD_LINE.search(ln))
    text = _INLINE_CODE.sub("[code removed]", text)
    text = _INLINE_CMD.sub("[command removed]", text)
    return " ".join(text.split())[:limit]


def make_item(source: str, url: str, title: str, body: str, credibility: float, *,
              confirmed: bool = True, cwes: list[str] | None = None,
              packages: list[dict[str, str]] | None = None, published: str = "",
              kev: bool = False, fixed: str | None = None,
              keep_summary: bool = True) -> IntelItem:
    title = strip_payloads(title, 300)
    summary = strip_payloads(body) if keep_summary else ""
    text = f"{title} {body}"
    cves = sorted(set(CVE_RE.findall(text)))
    cwe_list = sorted(set((cwes or []) + CWE_RE.findall(text)))
    digest = hashlib.sha256(f"{source}|{url}|{title}".encode()).hexdigest()[:24]
    return IntelItem(source=source, url=url, title=title, summary=summary, cve_ids=cves,
                     packages=packages or [], cwes=cwe_list, published=published,
                     credibility=credibility, confirmed=confirmed, kev=kev,
                     fixed_version=fixed, content_hash=digest)


class Collector(ABC):
    name = "base"
    confirmed = True

    def __init__(self, cfg: dict[str, Any], http: SafeClient):
        self.cfg = cfg
        self.http = http
        self.credibility = float(cfg.get("credibility", 0.5))

    def enabled(self) -> bool:
        return bool(self.cfg.get("enabled", False))

    def fetch(self, inventory: list[Dependency]) -> list[IntelItem]:
        return self.parse(self.get(inventory))

    @abstractmethod
    def get(self, inventory: list[Dependency]) -> Any:
        """Network call. Uses config URLs only."""

    @abstractmethod
    def parse(self, raw: Any) -> list[IntelItem]:
        """Pure function from a raw response to IntelItems; tested offline."""
