"""RSS/Atom collectors: oss-security, Exploit-DB metadata, Project Zero, vendor feeds.

XML is parsed with defusedxml. For Exploit-DB only titles and links are kept; entry bodies
are dropped so exploit code is never stored.
"""

from __future__ import annotations

from typing import Any

from defusedxml import ElementTree

from rce_sentinel.intel.base import Collector, make_item
from rce_sentinel.models import Dependency, IntelItem

ATOM = "{http://www.w3.org/2005/Atom}"


def parse_feed(xml_text: str) -> list[dict[str, str]]:
    root = ElementTree.fromstring(xml_text)
    entries = []
    for item in root.iter("item"):
        entries.append({"title": item.findtext("title") or "",
                        "link": item.findtext("link") or "",
                        "body": item.findtext("description") or "",
                        "published": item.findtext("pubDate") or ""})
    for entry in root.iter(f"{ATOM}entry"):
        link = entry.find(f"{ATOM}link[@rel='alternate']")
        if link is None:
            link = entry.find(f"{ATOM}link")
        entries.append({
            "title": entry.findtext(f"{ATOM}title") or "",
            "link": link.get("href", "") if link is not None else "",
            "body": entry.findtext(f"{ATOM}summary") or entry.findtext(f"{ATOM}content") or "",
            "published": entry.findtext(f"{ATOM}published") or "",
        })
    return entries


class RssCollector(Collector):
    keep_body = True

    def __init__(self, name: str, cfg: dict[str, Any], http: Any):
        super().__init__(cfg, http)
        self.name = name
        self.keep_body = name != "exploitdb"

    def urls(self) -> list[str]:
        return list(self.cfg.get("urls") or [self.cfg["url"]])

    def get(self, inventory: list[Dependency]) -> Any:
        out = []
        for url in self.urls():
            resp = self.http.request("GET", url)
            resp.raise_for_status()
            out.append(resp.text)
        return out

    def parse(self, raw: Any) -> list[IntelItem]:
        items = []
        for xml_text in raw:
            for e in parse_feed(xml_text):
                items.append(make_item(self.name, e["link"], e["title"],
                                       e["body"] if self.keep_body else "", self.credibility,
                                       published=e["published"], keep_summary=self.keep_body))
        return items
