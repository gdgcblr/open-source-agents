from __future__ import annotations

import ipaddress
import ssl
from pathlib import Path
from urllib.parse import urlsplit

import httpx

MAX_BYTES = 262_144


def project_file(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Path leaves project root: {relative}")
    return path


def read_document(root: Path, relative: str) -> str:
    path = project_file(root, relative)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError(f"Document exceeds {MAX_BYTES} bytes: {relative}")
    return path.read_text(encoding="utf-8")


def validate_url(url: str, *, allow_remote: bool = False, allow_http: bool = False) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Use an HTTP(S) base URL without credentials, query, or fragment")
    # Validate the port now, rather than deferring failure to the client.
    _ = parsed.port
    try:
        loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        loopback = parsed.hostname == "localhost"
    if not loopback and not allow_remote:
        raise ValueError("Remote network access requires explicit approval")
    if parsed.scheme == "http" and not loopback and not allow_http:
        raise ValueError("Remote plaintext HTTP requires explicit approval; prefer HTTPS")
    return url.rstrip("/")


def http_client(timeout: float = 10) -> httpx.Client:
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    return httpx.Client(timeout=timeout, verify=context, trust_env=False, follow_redirects=False)


def bounded_body(response: httpx.Response) -> bytes:
    data = bytearray()
    for chunk in response.iter_bytes():
        data.extend(chunk)
        if len(data) > MAX_BYTES:
            raise ValueError(f"Response exceeds {MAX_BYTES} bytes")
    return bytes(data)
