"""Check that the documentation each profile cites still exists and still says it.

This is the only part of the tool that uses the network, and it only runs when
you call ``prompt-enhancer sources check``. For every cited URL it:

* fetches the page (https only, allowlisted official hosts, size and time limits),
* checks that every section heading the profile's guidelines cite is still present,
* fingerprints the visible text and compares it with the previous run, cached in
  ``$PROMPT_ENHANCER_CACHE_DIR`` (default ``~/.cache/prompt-enhancer``).

It does not rewrite profiles. A changed page or missing section is a signal for
a human to re-read the docs and bump the profile version.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from collections.abc import Callable
from urllib.parse import urlparse

from . import registry

MAX_BYTES = 5_000_000
TIMEOUT_S = 20
USER_AGENT = "model-aware-prompt-enhancer/0.3 (+https://github.com/gdgcblr/open-source-agents)"

Fetcher = Callable[[str], str]


def cache_dir() -> Path:
    return Path(os.environ.get("PROMPT_ENHANCER_CACHE_DIR", "~/.cache/prompt-enhancer")).expanduser()


def _check_url(url: str) -> None:
    p = urlparse(url)
    if p.scheme != "https":
        raise ValueError(f"refusing non-https URL: {url}")
    if p.hostname not in registry.OFFICIAL_DOC_HOSTS:
        raise ValueError(f"refusing non-allowlisted host: {p.hostname}")


def fetch(url: str) -> str:
    _check_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310 - scheme and host validated above
        final = resp.geturl()
        _check_url(final)  # do not follow redirects off the allowlist
        data = resp.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"response larger than {MAX_BYTES} bytes")
    return data.decode("utf-8", errors="replace")


def visible_text(page: str) -> str:
    page = re.sub(r"<(script|style|noscript|svg)\b.*?</\1>", " ", page, flags=re.S | re.I)
    page = re.sub(r"<[^>]+>", " ", page)
    return re.sub(r"\s+", " ", html.unescape(page)).strip()


def _section_present(section: str, text: str) -> bool:
    # "Gemini 3 > Core prompting principles" -> check the most specific part.
    leaf = section.split(">")[-1].strip()
    return leaf.lower() in text.lower() if leaf else True


def check(fetcher: Fetcher = fetch, use_cache: bool = True) -> list[dict[str, Any]]:
    """Return one report row per cited URL."""
    wanted: dict[str, set[str]] = {}
    for prof in registry.load_models().values():
        for s in prof.sources:
            wanted.setdefault(s.url, set())
        items = list(prof.guidelines) + [g for v in prof.variants for g in v.guidelines]
        for g in items:
            if g.section:
                wanted[g.source.url].add(g.section)

    cache_file = cache_dir() / "sources.json"
    previous: dict[str, Any] = {}
    if use_cache and cache_file.exists():
        try:
            previous = json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = {}

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows: list[dict[str, Any]] = []
    for url, sections in sorted(wanted.items()):
        row: dict[str, Any] = {"url": url, "checked_at": now}
        try:
            text = visible_text(fetcher(url))
        except Exception as e:  # report and continue with other sources
            row.update(status="error", error=f"{type(e).__name__}: {e}")
            rows.append(row)
            continue
        digest = hashlib.sha256(text.encode()).hexdigest()
        missing = sorted(s for s in sections if not _section_present(s, text))
        prev = previous.get(url, {}).get("sha256")
        row.update(
            status="ok" if not missing else "sections-missing",
            sha256=digest,
            changed_since_last_check=None if prev is None else prev != digest,
            sections_checked=len(sections),
            missing_sections=missing,
        )
        rows.append(row)

    if use_cache:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        merged = dict(previous)
        merged.update({r["url"]: {"sha256": r["sha256"], "checked_at": r["checked_at"]} for r in rows if "sha256" in r})
        cache_file.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return rows
