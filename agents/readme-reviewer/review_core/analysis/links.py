"""Broken-link check for URLs in a project's README.

The README is untrusted input, so this only makes plain HTTP(S) requests with the
standard library, skips private/loopback addresses (no SSRF), never follows
redirects, and caps how many URLs it checks.
"""

import ipaddress
import re
import socket
import ssl
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from .tools import _check_dir

MAX_URLS = 20
TIMEOUT_SECONDS = 5
URL_PATTERN = re.compile(r"https?://[^\s)\]\"'`]+")
# Servers often answer 401/403/405/429 to scripts even though the page exists.
REACHABLE_BUT_UNVERIFIED = {401, 403, 405, 429, 999}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Treat a redirect as an answer instead of following it to an unchecked host."""

    def redirect_request(self, *args, **kwargs):
        return None


def extract_urls(text: str) -> list:
    """Unique clickable URLs in order of appearance.

    URLs inside code (API endpoints, example commands) are not links a reader clicks,
    so they are ignored, as are template placeholders like <user>.
    """
    text = re.sub(r"`[^`\n]*`", "", re.sub(r"```.*?```", "", text, flags=re.DOTALL))
    seen, urls = set(), []
    for match in URL_PATTERN.findall(text):
        url = match.rstrip(".,;:")
        if re.search(r"[<>{}$]", url) or url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def _is_public_host(host: str) -> bool:
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except socket.gaierror:
        return True  # unresolvable: let the request report it as a network error
    return all(ipaddress.ip_address(a).is_global for a in addresses)


def _tls_context() -> ssl.SSLContext:
    """Verifying TLS context. Uses certifi's CA bundle when installed (python.org builds on
    macOS often ship without system certificates). Verification is never turned off."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _request(url: str, method: str) -> int:
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=_tls_context()))
    req = urllib.request.Request(url, method=method, headers={"User-Agent": "readme-reviewer-link-check"})
    try:
        with opener.open(req, timeout=TIMEOUT_SECONDS) as response:
            return response.status
    except urllib.error.HTTPError as err:
        return err.code


def _fetch_status(url: str) -> int:
    """HTTP status for a URL; retries with GET when HEAD is not allowed."""
    status = _request(url, "HEAD")
    if status in (403, 405, 501):
        status = _request(url, "GET")
    return status


def _check_one(url: str) -> dict:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return {"url": url, "state": "skipped", "reason": "not an http(s) URL"}
    if not _is_public_host(parsed.hostname):
        return {"url": url, "state": "skipped", "reason": "private or local address is not checked"}
    try:
        status = _fetch_status(url)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        if isinstance(getattr(exc, "reason", exc), ssl.SSLCertVerificationError):
            # Our machine cannot verify the certificate; that says nothing about the link.
            return {"url": url, "state": "skipped", "reason": "TLS certificate could not be verified here"}
        return {"url": url, "state": "broken", "reason": f"network error: {exc}"}
    if status < 400 or status in REACHABLE_BUT_UNVERIFIED:
        return {"url": url, "state": "ok", "reason": f"HTTP {status}"}
    return {"url": url, "state": "broken", "reason": f"HTTP {status}"}


def check_links(path: str) -> dict:
    """Check that http(s) URLs in the project README respond (not 404/5xx).

    Args:
        path: Folder name or path of the project to review.
    """
    root, err = _check_dir(path)
    if err:
        return err
    readme = root / "README.md"
    if not readme.is_file():
        return {"checked": 0, "broken": [], "skipped": [], "truncated": False, "passed": True,
                "reason": "No README.md to check."}
    urls = extract_urls(readme.read_text(encoding="utf-8", errors="replace"))
    to_check = urls[:MAX_URLS]
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(_check_one, to_check))
    broken = [r for r in results if r["state"] == "broken"]
    skipped = [r for r in results if r["state"] == "skipped"]
    return {
        "checked": len(results) - len(skipped),
        "broken": broken,
        "skipped": skipped,
        "truncated": len(urls) > MAX_URLS,
        "passed": not broken,
        "reason": "All checked links respond." if not broken else f"{len(broken)} broken link(s).",
    }
