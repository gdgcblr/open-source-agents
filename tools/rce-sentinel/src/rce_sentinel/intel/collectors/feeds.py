"""Official structured feeds: CISA KEV, NVD, GitHub Security Advisories, OSV."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from rce_sentinel.intel.base import Collector, make_item
from rce_sentinel.models import Dependency, IntelItem

GHSA_ECOSYSTEMS = {"pip": "PyPI", "npm": "npm", "go": "Go", "rust": "crates.io",
                   "maven": "Maven", "rubygems": "RubyGems", "nuget": "NuGet",
                   "composer": "Packagist"}


class CisaKev(Collector):
    name = "cisa_kev"

    def get(self, inventory: list[Dependency]) -> Any:
        return self.http.get_json(self.cfg["url"])

    def parse(self, raw: Any, lookback_days: int = 30) -> list[IntelItem]:
        cutoff = (datetime.now(UTC) - timedelta(days=lookback_days)).date().isoformat()
        out = []
        for v in raw.get("vulnerabilities", []):
            if lookback_days and v.get("dateAdded", "") < cutoff:
                continue
            product = (v.get("product") or "").lower()
            out.append(make_item(
                self.name, f"https://nvd.nist.gov/vuln/detail/{v['cveID']}",
                f"{v['cveID']} {v.get('vulnerabilityName', '')}",
                v.get("shortDescription", ""), self.credibility,
                cwes=v.get("cwes", []), published=v.get("dateAdded", ""), kev=True,
                packages=[{"ecosystem": "product", "name": product,
                           "vendor": (v.get("vendorProject") or "").lower()}]))
        return out


class Nvd(Collector):
    name = "nvd"

    def get(self, inventory: list[Dependency]) -> Any:
        end = datetime.now(UTC)
        start = end - timedelta(hours=int(self.cfg.get("lookback_hours", 48)))
        fmt = "%Y-%m-%dT%H:%M:%S.000"
        params = {"pubStartDate": start.strftime(fmt), "pubEndDate": end.strftime(fmt),
                  "resultsPerPage": 200}
        return self.http.get_json(self.cfg["url"], params=params)

    def parse(self, raw: Any) -> list[IntelItem]:
        out = []
        for entry in raw.get("vulnerabilities", []):
            cve = entry.get("cve", {})
            desc = next((d["value"] for d in cve.get("descriptions", [])
                         if d.get("lang") == "en"), "")
            cwes = [d["value"] for w in cve.get("weaknesses", [])
                    for d in w.get("description", []) if d["value"].startswith("CWE-")]
            products = set()
            for conf in cve.get("configurations", []):
                for node in conf.get("nodes", []):
                    for m in node.get("cpeMatch", []):
                        parts = m.get("criteria", "").split(":")
                        if len(parts) > 5:
                            products.add((parts[3], parts[4]))
            out.append(make_item(
                self.name, f"https://nvd.nist.gov/vuln/detail/{cve.get('id')}",
                cve.get("id", ""), desc, self.credibility, cwes=cwes,
                published=cve.get("published", ""),
                packages=[{"ecosystem": "product", "name": p, "vendor": v}
                          for v, p in sorted(products)]))
        return out


class Ghsa(Collector):
    name = "ghsa"

    def get(self, inventory: list[Dependency]) -> Any:
        import os

        headers = {"Accept": "application/vnd.github+json"}
        if token := os.environ.get(self.cfg.get("token_env", "")):
            headers["Authorization"] = f"Bearer {token}"
        return self.http.get_json(self.cfg["url"], headers=headers)

    def parse(self, raw: Any) -> list[IntelItem]:
        out = []
        for adv in raw or []:
            pkgs, fixed = [], None
            for v in adv.get("vulnerabilities", []) or []:
                pkg = v.get("package") or {}
                eco = GHSA_ECOSYSTEMS.get(pkg.get("ecosystem", ""), pkg.get("ecosystem", ""))
                pkgs.append({"ecosystem": eco, "name": (pkg.get("name") or "").lower(),
                             "range": v.get("vulnerable_version_range") or ""})
                fixed = fixed or v.get("first_patched_version")
            cwes = [c["cwe_id"] for c in adv.get("cwes", []) or [] if c.get("cwe_id")]
            title = f"{adv.get('ghsa_id')} {adv.get('cve_id') or ''} {adv.get('summary', '')}"
            out.append(make_item(self.name, adv.get("html_url", ""), title,
                                 adv.get("description", ""), self.credibility, cwes=cwes,
                                 packages=pkgs, published=adv.get("published_at", ""),
                                 fixed=fixed))
        return out


class OsvTargeted(Collector):
    """Queries OSV for this repo's own SBOM instead of the global firehose."""

    name = "osv"

    def get(self, inventory: list[Dependency]) -> Any:
        pinned = [d for d in inventory if d.version]
        if not pinned:
            return {"results": [], "deps": []}
        payload = {"queries": [{"package": {"name": d.name, "ecosystem": d.ecosystem},
                                "version": d.version} for d in pinned]}
        data = self.http.post_json(self.cfg["url"], payload)
        data["deps"] = [d.model_dump() for d in pinned]
        return data

    def parse(self, raw: Any) -> list[IntelItem]:
        out = []
        for dep, res in zip(raw.get("deps", []), raw.get("results", []), strict=False):
            for v in res.get("vulns", []):
                out.append(make_item(
                    self.name, f"https://osv.dev/vulnerability/{v['id']}", v["id"], "",
                    self.credibility, published=v.get("modified", ""),
                    packages=[{"ecosystem": dep["ecosystem"], "name": dep["name"]}]))
        return out
