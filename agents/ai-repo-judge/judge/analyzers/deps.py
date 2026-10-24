"""Known-vulnerability lookup for exactly pinned dependencies via the free OSV.dev batch API."""

from __future__ import annotations

import logging

import httpx

from judge.analyzers.manifest import Dep

log = logging.getLogger(__name__)
OSV_BATCH = "https://api.osv.dev/v1/querybatch"
_cache: dict[tuple[str, str, str], list[str]] = {}


def known_vulnerabilities(deps: list[Dep]) -> dict[Dep, list[str]] | None:
    """Map each vulnerable dep to its advisory IDs. None means the lookup could not run."""
    exact = [d for d in deps if d.exact_version]
    todo = [d for d in exact if (d.ecosystem, d.name.lower(), d.exact_version) not in _cache]
    if todo:
        queries = [{"package": {"name": d.name, "ecosystem": d.ecosystem}, "version": d.exact_version} for d in todo]
        try:
            resp = httpx.post(OSV_BATCH, json={"queries": queries}, timeout=20)
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("OSV lookup failed: %s", exc)
            return None
        for d, res in zip(todo, results, strict=False):
            _cache[(d.ecosystem, d.name.lower(), d.exact_version or "")] = [v["id"] for v in res.get("vulns", [])]
    out: dict[Dep, list[str]] = {}
    for d in exact:
        ids = _cache.get((d.ecosystem, d.name.lower(), d.exact_version or ""), [])
        if ids:
            out[d] = ids
    return out
