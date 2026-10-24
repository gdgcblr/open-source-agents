"""Strict, branch-scoped advisory matching. Never infer universal safety."""
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from .config import advisory_path, bounded_int


def version_tuple(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not re.fullmatch(r"(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})\.(0|[1-9][0-9]{0,3})", value):
        raise ValueError("Use an exact upstream stable version: major.minor.patch")
    return tuple(int(n) for n in value.split("."))


def _official_url(value: str, product: str) -> bool:
    parsed = urlparse(value)
    allowed = (parsed.hostname == "www.php.net" or
               (parsed.hostname == "github.com" and parsed.path.startswith("/php/php-src/security/advisories/"))) if product == "php" else parsed.hostname == "nodejs.org"
    return parsed.scheme == "https" and allowed and not parsed.username and not parsed.password


def load_catalog(path: Path | None = None, today: date | None = None) -> tuple[dict | None, str | None]:
    today = today or datetime.now(timezone.utc).date()
    try:
        with (path or advisory_path()).open("rb") as stream:
            raw = stream.read(250_001)
        if len(raw) > 250_000:
            raise ValueError
        data = json.loads(raw)
        if type(data["schema_version"]) is not int or data["schema_version"] != 1 or not data["records"] or len(data["records"]) > 100:
            raise ValueError
        checked = date.fromisoformat(data["verified_on"])
        if checked > today:
            raise ValueError
        ids = set()
        for record in data["records"]:
            if record["cve"] in ids or not re.fullmatch(r"CVE-\d{4}-\d{4,}", record["cve"]):
                raise ValueError
            ids.add(record["cve"])
            if record["product"] not in {"php", "nodejs"} or record["verified"] is not True:
                raise ValueError
            if record["severity"] not in {None, "low", "medium", "high", "critical"}:
                raise ValueError
            if not _official_url(record["source_url"], record["product"]):
                raise ValueError
            if date.fromisoformat(record["published"]) > checked or not record["ranges"]:
                raise ValueError
            spans = []
            for span in record["ranges"]:
                lower, fixed, upper = (version_tuple(span[k]) for k in ("introduced", "fixed", "branch_end"))
                if not lower < fixed < upper:
                    raise ValueError
                spans.append((lower, upper))
            spans.sort()
            if any(right[0] < left[1] for left, right in zip(spans, spans[1:])):
                raise ValueError
        for notice in data.get("notices", []):
            if notice["product"] not in {"php", "nodejs"} or not _official_url(notice["source_url"], notice["product"]):
                raise ValueError
            if date.fromisoformat(notice["published"]) > checked or not isinstance(notice["note"], str):
                raise ValueError
        stale = (today - checked).days > bounded_int("TRIAGE_ADVISORY_MAX_AGE_DAYS", 7, 90)
        return data, "Advisory snapshot is stale; manually verify current publisher advisories." if stale else None
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return None, "Advisory data is missing, malformed, unverified, or configuration is invalid; manually verify publisher advisories."


def match_runtime(product: str, version: str, *, path: Path | None = None, today: date | None = None) -> dict:
    catalog, issue = load_catalog(path, today)
    result = {"status": "UNKNOWN", "matches": [], "issues": [issue] if issue else [],
              "scope": "Only the curated CVEs and explicitly listed upstream branches; never a security clearance."}
    try:
        parsed = version_tuple(version)
        if product not in {"php", "nodejs"}:
            raise ValueError
    except ValueError:
        result["issues"].append("Missing or unsupported runtime/version; supply php or nodejs and an exact stable upstream version.")
        return result
    if catalog is None:
        return result
    result["verified_on"] = catalog["verified_on"]
    result["notices"] = [n for n in catalog.get("notices", []) if n["product"] == product]
    for record in catalog["records"]:
        if record["product"] != product:
            continue
        for span in record["ranges"]:
            if version_tuple(span["introduced"]) <= parsed < version_tuple(span["branch_end"]):
                result["matches"].append({**record, "matched_range": span,
                    "status": "AFFECTED" if parsed < version_tuple(span["fixed"]) else "FIXED"})
                break
    if not result["matches"]:
        result["issues"].append("Runtime branch is outside the curated coverage; verify vendor/backport status manually.")
    elif issue is None:
        result["status"] = "AFFECTED" if any(m["status"] == "AFFECTED" for m in result["matches"]) else "FIXED"
    return result
