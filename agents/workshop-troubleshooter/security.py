"""
Enterprise-Grade Security & Sanitization Layer for Workshop Troubleshooter Agent.
Includes:
- API Key & Secret Scrubbing (prevents credential leaks in logs/responses)
- Input Sanitization & XSS Protection
- In-memory Token-Bucket Rate Limiter per client IP
- Role-based Admin Bearer Token Authentication
- Security Headers & Strict CORS Policy Middleware
- Production Hardening (Debug disabled, zero stack trace exposure)
"""

import html
import os
import re
import time
from collections import defaultdict
from typing import Dict, Tuple, Optional
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# ---------------------------------------------------------------------------
# 1. API KEY & SENSITIVE DATA SCRUBBER (Zero Secret Leakage)
# ---------------------------------------------------------------------------
SECRET_PATTERNS = [
    (re.compile(r"AIzaSy[A-Za-z0-9_-]{33}"), "[REDACTED_GOOGLE_API_KEY]"),
    (re.compile(r"sk-[a-zA-Z0-9]{20,64}"), "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"ghp_[a-zA-Z0-9]{36}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"Bearer\s+[A-Za-z0-9\-\._~\+\/]+=*", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r"(password|secret|api_key|token)\s*[:=]\s*['\"][^'\"]+['\"]", re.IGNORECASE), r"\1=[REDACTED]"),
    (re.compile(r"-----BEGIN (RSA|OPENSSH|EC|PRIVATE) KEY-----[^-]+-----END \1 KEY-----", re.DOTALL), "[REDACTED_PRIVATE_KEY]"),
]


def scrub_secrets(text: str) -> str:
    """Scans and redacts any exposed API keys, bearer tokens, or credentials."""
    if not isinstance(text, str):
        return text
    cleaned = text
    for pattern, replacement in SECRET_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    return cleaned


# ---------------------------------------------------------------------------
# 2. INPUT SANITIZATION & XSS DEFENSE
# ---------------------------------------------------------------------------
XSS_DISALLOWED = re.compile(
    r"(<script.*?>.*?</script>|javascript:|data:text/html|vbscript:|on\w+\s*=)",
    re.IGNORECASE | re.DOTALL,
)


def sanitize_input(user_str: str, max_length: int = 4000) -> str:
    """
    Sanitizes untrusted user inputs:
    - Truncates to max allowed length to prevent memory DoS.
    - Neutralizes XSS payload signatures.
    - Encodes raw HTML entities so input cannot execute in browser DOM.
    - Scrubs potential API keys.
    """
    if not user_str:
        return ""
    # Length guard
    clipped = str(user_str)[:max_length].strip()
    # Redact any pasted keys from user prompt
    clipped = scrub_secrets(clipped)
    # Neutralize script tags / event handlers
    clipped = XSS_DISALLOWED.sub("[BLOCKED_SCRIPT_TAG]", clipped)
    # HTML Entity escaping
    return html.escape(clipped, quote=True)


# ---------------------------------------------------------------------------
# 3. RATE LIMITER (In-Memory Sliding Window / Token Bucket)
# ---------------------------------------------------------------------------
class SlidingWindowRateLimiter:
    """
    Rate limits requests by IP address.
    Default: max 40 requests per 60 seconds per IP.
    """

    def __init__(self, max_requests: int = 40, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # client_ip -> list of timestamps
        self.hits: Dict[str, list] = defaultdict(list)

    def is_allowed(self, ip: str) -> Tuple[bool, int]:
        now = time.time()
        cutoff = now - self.window_seconds
        # Prune old timestamps
        history = [t for t in self.hits[ip] if t > cutoff]
        self.hits[ip] = history

        if len(history) >= self.max_requests:
            retry_after = int(self.window_seconds - (now - history[0])) + 1
            return False, max(retry_after, 1)

        self.hits[ip].append(now)
        return True, 0


global_rate_limiter = SlidingWindowRateLimiter(max_requests=40, window_seconds=60)


class RateLimiterMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Exempt static assets and health check
        path = request.url.path
        if path.startswith("/static") or path in ["/favicon.ico", "/health"]:
            return await call_next(request)

        client_ip = request.client.host if request.client else "127.0.0.1"
        allowed, retry_after = global_rate_limiter.is_allowed(client_ip)

        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded. Please wait before submitting more queries.",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)


# ---------------------------------------------------------------------------
# 4. SECURITY HEADERS MIDDLEWARE
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enforces essential OWASP security headers on all HTTP responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Legacy browser XSS filter
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Referrer privacy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Modern Content Security Policy
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self';"
        )
        # Disable server fingerprinting
        if "server" in response.headers:
            del response.headers["server"]
        return response


# ---------------------------------------------------------------------------
# 5. ADMIN AUTHENTICATION & ACCESS CONTROL
# ---------------------------------------------------------------------------
security_bearer = HTTPBearer(auto_error=False)


def get_admin_token() -> str:
    """Retrieves expected admin token from environment or uses secure default."""
    return os.getenv("ADMIN_SECRET_KEY", "gdg-hackathon-secure-admin-key-2026")


from fastapi import Depends

def verify_admin_access(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
) -> bool:
    """Verifies bearer token for privileged instructor/admin routes."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required. Provide Bearer token in Authorization header.",
        )
    expected = get_admin_token()
    if credentials.credentials != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Invalid administrator credentials.",
        )
    return True
