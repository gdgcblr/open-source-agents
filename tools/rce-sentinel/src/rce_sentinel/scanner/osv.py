"""OSV.dev lookups with a local SQLite cache, plus KEV and EPSS enrichment.

Online: querybatch, then fetch missing records. Offline: match versions locally against
cached or seeded OSV records. Only RCE-class advisories are kept.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

from packaging.version import InvalidVersion, Version

from rce_sentinel.memory.store import Store
from rce_sentinel.models import Advisory, Dependency
from rce_sentinel.netio import SafeClient

OSV_BATCH = "https://api.osv.dev/v1/querybatch"
OSV_VULN = "https://api.osv.dev/v1/vulns/{id}"
EPSS_URL = "https://api.first.org/data/v1/epss?cve={cves}"
KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
QUERY_TTL = 24 * 3600

RCE_CWES = {"CWE-78", "CWE-77", "CWE-94", "CWE-95", "CWE-502", "CWE-917", "CWE-1336"}
RCE_TEXT = re.compile(
    r"remote code execution|arbitrary code|code execution|command injection|"
    r"execute arbitrary|arbitrary command|deserializ\w+ of untrusted|template injection",
    re.I,
)
EXEC_TEXT = re.compile(r"execut|webshell|web shell|run code", re.I)


def is_rce(cwes: list[str], text: str) -> bool:
    if RCE_CWES.intersection(cwes):
        return True
    if "CWE-434" in cwes and EXEC_TEXT.search(text):
        return True
    return bool(RCE_TEXT.search(text))


def _ver_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)) or (0,)


def _lt(a: str, b: str) -> bool:
    try:
        return Version(a.lstrip("v")) < Version(b.lstrip("v"))
    except InvalidVersion:
        return _ver_tuple(a) < _ver_tuple(b)


def affected_entry(record: dict[str, Any], dep: Dependency) -> dict[str, Any] | None:
    for aff in record.get("affected", []):
        pkg = aff.get("package", {})
        name = pkg.get("name", "")
        if pkg.get("ecosystem") != dep.ecosystem:
            continue
        if (name.lower() if dep.ecosystem == "PyPI" else name) == dep.name:
            return aff
    return None


def version_affected(aff: dict[str, Any], version: str) -> bool:
    if version in aff.get("versions", []):
        return True
    for rng in aff.get("ranges", []):
        if rng.get("type") not in {"ECOSYSTEM", "SEMVER"}:
            continue
        inside = False
        for ev in rng.get("events", []):
            if "introduced" in ev:
                intro = ev["introduced"]
                inside = intro == "0" or not _lt(version, intro)
            elif inside and (
                ("fixed" in ev and not _lt(version, ev["fixed"]))
                or ("last_affected" in ev and _lt(ev["last_affected"], version))
            ):
                inside = False
        if inside:
            return True
    return False


def fixed_version(aff: dict[str, Any], version: str | None) -> str | None:
    fixes = [ev["fixed"] for r in aff.get("ranges", []) for ev in r.get("events", [])
             if "fixed" in ev]
    if version:
        fixes = [f for f in fixes if _lt(version, f)] or fixes
    return min(fixes, key=_ver_tuple) if fixes else None


def to_advisory(record: dict[str, Any], dep: Dependency, overlay: dict[str, Any]) -> Advisory:
    aff = affected_entry(record, dep) or {}
    cwes = list(record.get("database_specific", {}).get("cwe_ids", []) or [])
    vector = next((s["score"] for s in record.get("severity", [])
                   if s.get("type") == "CVSS_V3"), None)
    eco = aff.get("ecosystem_specific") or {}
    symbols: list[str] = list(eco.get("affected_functions", []) or [])
    for imp in eco.get("imports", []) or []:
        symbols += [f"{imp.get('path', '')}.{s}" for s in imp.get("symbols", [])]
    for key in [record["id"], *record.get("aliases", [])]:
        symbols += overlay.get(key, []) or []
    return Advisory(
        id=record["id"],
        aliases=record.get("aliases", []),
        summary=(record.get("summary") or record.get("details", ""))[:300],
        cwes=cwes,
        cvss_vector=vector,
        fixed_version=fixed_version(aff, dep.version),
        symbols=sorted(set(symbols)),
        references=[r["url"] for r in record.get("references", [])[:3]],
    )


class OsvClient:
    def __init__(self, store: Store, http: SafeClient | None, overlay: dict[str, Any]):
        self.store = store
        self.http = http
        self.overlay = overlay
        self.online_errors: list[str] = []

    # --- cache management ----------------------------------------------------
    def put_record(self, record: dict[str, Any]) -> None:
        pkgs = " ".join(
            f"{a.get('package', {}).get('ecosystem')}|"
            f"{a.get('package', {}).get('name', '').lower()}"
            for a in record.get("affected", [])
        )
        self.store.execute(
            "INSERT OR REPLACE INTO vulns(id, modified, pkgs, json) VALUES (?,?,?,?)",
            (record["id"], record.get("modified", ""), f" {pkgs} ", json.dumps(record)),
        )

    def import_seed(self, records: list[dict[str, Any]]) -> int:
        for r in records:
            self.put_record(r)
        return len(records)

    def _record(self, vid: str) -> dict[str, Any] | None:
        rows = self.store.execute("SELECT json FROM vulns WHERE id=?", (vid,))
        if rows:
            return json.loads(rows[0]["json"])
        if self.http is None:
            return None
        try:
            rec = self.http.get_json(OSV_VULN.format(id=vid))
        except Exception as exc:  # network errors degrade to cache-only
            self.online_errors.append(f"osv vuln {vid}: {type(exc).__name__}")
            return None
        self.put_record(rec)
        return rec

    def _local_ids(self, dep: Dependency) -> list[str]:
        key = f"% {dep.ecosystem}|{dep.name.lower()} %"
        rows = self.store.execute("SELECT id, json FROM vulns WHERE pkgs LIKE ?", (key,))
        out = []
        for row in rows:
            rec = json.loads(row["json"])
            aff = affected_entry(rec, dep)
            if aff and dep.version and version_affected(aff, dep.version):
                out.append(row["id"])
        return out

    def _query_online(self, deps: list[Dependency]) -> None:
        if self.http is None or not deps:
            return
        payload = {"queries": [{"package": {"name": d.name, "ecosystem": d.ecosystem},
                                "version": d.version} for d in deps]}
        try:
            data = self.http.post_json(OSV_BATCH, payload)
        except Exception as exc:
            self.online_errors.append(f"osv querybatch: {type(exc).__name__}")
            return
        for dep, res in zip(deps, data.get("results", []), strict=False):
            ids = [v["id"] for v in res.get("vulns", [])]
            self.store.execute("INSERT OR REPLACE INTO osv_queries VALUES (?,?,?)",
                               (self._qkey(dep), json.dumps(ids), time.time()))

    @staticmethod
    def _qkey(dep: Dependency) -> str:
        return f"{dep.ecosystem}|{dep.name}|{dep.version}"

    # --- public --------------------------------------------------------------
    def lookup(self, deps: list[Dependency]) -> dict[str, list[Advisory]]:
        """{dep key: RCE-class advisories} for pinned dependencies."""
        pinned = [d for d in deps if d.version]
        stale = []
        for d in pinned:
            rows = self.store.execute("SELECT fetched_at FROM osv_queries WHERE key=?",
                                      (self._qkey(d),))
            if not rows or time.time() - rows[0]["fetched_at"] > QUERY_TTL:
                stale.append(d)
        self._query_online(stale)
        out: dict[str, list[Advisory]] = {}
        for d in pinned:
            rows = self.store.execute("SELECT vuln_ids FROM osv_queries WHERE key=?",
                                      (self._qkey(d),))
            ids = set(json.loads(rows[0]["vuln_ids"])) if rows else set()
            ids |= set(self._local_ids(d))
            advs = []
            seen_cves: set[str] = set()
            for vid in sorted(ids, key=lambda i: (not i.startswith("GHSA"), i)):
                rec = self._record(vid)
                if not rec:
                    continue
                adv = to_advisory(rec, d, self.overlay)
                text = f"{rec.get('summary', '')} {rec.get('details', '')}"
                if not is_rce(adv.cwes, text):
                    continue
                if seen_cves.intersection(adv.cve_ids):  # PYSEC/GHSA duplicates
                    continue
                seen_cves.update(adv.cve_ids)
                advs.append(adv)
            out[self._qkey(d)] = advs
        return out

    def db_version(self) -> str:
        row = self.store.execute("SELECT COUNT(*) AS n, MAX(modified) AS m FROM vulns")[0]
        kev = self.store.execute(
            "SELECT COUNT(*) AS n, MAX(catalog_version) AS v, SUM(simulated) AS s FROM kev")[0]
        raw = f"{row['n']}|{row['m']}|{kev['n']}|{kev['v']}|{kev['s']}"
        return hashlib.sha256(raw.encode()).hexdigest()[:12]


class ThreatFeeds:
    """CISA KEV membership and FIRST EPSS scores, cached in SQLite."""

    def __init__(self, store: Store, http: SafeClient | None):
        self.store = store
        self.http = http

    def refresh_kev(self) -> int:
        if self.http is None:
            return 0
        data = self.http.get_json(KEV_URL)
        version = data.get("catalogVersion", "")
        for v in data.get("vulnerabilities", []):
            self.store.execute(
                "INSERT OR REPLACE INTO kev(cve, json, catalog_version, simulated) "
                "VALUES (?,?,?,0)", (v["cveID"], json.dumps(v), version))
        return len(data.get("vulnerabilities", []))

    def add_kev(self, entry: dict[str, Any], simulated: bool) -> None:
        self.store.execute(
            "INSERT OR REPLACE INTO kev(cve, json, catalog_version, simulated) VALUES (?,?,?,?)",
            (entry["cveID"], json.dumps(entry), entry.get("catalogVersion", "local"),
             int(simulated)))

    def in_kev(self, cves: list[str]) -> bool:
        return any(self.store.execute("SELECT 1 FROM kev WHERE cve=?", (c,)) for c in cves)

    def epss(self, cves: list[str]) -> float | None:
        best: float | None = None
        missing = []
        for c in cves:
            rows = self.store.execute("SELECT score FROM epss WHERE cve=?", (c,))
            if rows:
                best = max(best or 0.0, rows[0]["score"])
            else:
                missing.append(c)
        if missing and self.http is not None:
            try:
                data = self.http.get_json(EPSS_URL.format(cves=",".join(missing)))
                for item in data.get("data", []):
                    score = float(item["epss"])
                    self.store.execute("INSERT OR REPLACE INTO epss VALUES (?,?,?)",
                                       (item["cve"], score, time.time()))
                    best = max(best or 0.0, score)
            except Exception:  # EPSS is optional enrichment
                pass
        return best
