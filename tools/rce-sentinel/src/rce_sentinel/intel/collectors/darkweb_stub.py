"""Disabled-by-default interface stub. No crawler is implemented, on purpose.

Any implementation contributed here must:
- be passive and read-only: fetch pages, never post, register, log in, message, or buy;
- read only from an explicit allowlist the user supplies in sources.yaml (`darkweb.allowlist`),
  never discover or follow links;
- store metadata only (CVE ids, product names, a link), never payloads, dumps, or credentials;
- comply with the law where it runs and with the operator's own policy.

Reliable, legitimate intel for RCE disclosures already comes from CISA KEV, NVD, OSV, GHSA,
vendor advisories, oss-security, and Project Zero. Dark-web sources add legal and personal
safety risk and a lot of noise for little extra signal, so this project ships without one.
"""

from __future__ import annotations

from typing import Any

from rce_sentinel.intel.base import Collector
from rce_sentinel.models import Dependency, IntelItem


class DarkWebStub(Collector):
    name = "darkweb"
    confirmed = False

    def enabled(self) -> bool:
        return False

    def get(self, inventory: list[Dependency]) -> Any:
        raise NotImplementedError("no dark-web collector is implemented; see module docstring")

    def parse(self, raw: Any) -> list[IntelItem]:
        return []
