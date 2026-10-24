"""Authentication for the dashboard API and authenticity checks for Twilio traffic."""

import hashlib
import hmac
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from twilio.request_validator import RequestValidator

from app.dependencies import SettingsDep

_basic_auth = HTTPBasic(realm="Hospital Reception IVR")


def require_dashboard_user(
    credentials: Annotated[HTTPBasicCredentials, Depends(_basic_auth)],
    settings: SettingsDep,
) -> str:
    """HTTP Basic auth for the dashboard. Compares in constant time to avoid timing leaks."""
    username_ok = secrets.compare_digest(
        credentials.username.encode(), settings.dashboard_username.encode()
    )
    password_ok = secrets.compare_digest(
        credentials.password.encode(), settings.dashboard_password.get_secret_value().encode()
    )
    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": 'Basic realm="Hospital Reception IVR"'},
        )
    return credentials.username


async def verify_twilio_signature(request: Request, settings: SettingsDep) -> None:
    """Reject webhook requests that were not signed by Twilio with our auth token.

    Twilio signs the exact public URL it called, so the URL is rebuilt from PUBLIC_BASE_URL
    rather than from the (possibly proxied) request URL.
    """
    if not settings.twilio_configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Twilio is not configured")
    if not settings.twilio_validate_signature:
        return

    url = settings.public_url(request.url.path)
    if request.url.query:
        url = f"{url}?{request.url.query}"
    form = await request.form()
    params = {key: value for key, value in form.items() if isinstance(value, str)}
    signature = request.headers.get("X-Twilio-Signature", "")

    validator = RequestValidator(settings.twilio_auth_token.get_secret_value())
    if not validator.validate(url, params, signature):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid Twilio signature")


def create_stream_token(call_sid: str, secret: str) -> str:
    """Token proving a Media Stream connection was requested by our own TwiML for this call."""
    return hmac.new(
        secret.encode(), f"media-stream:{call_sid}".encode(), hashlib.sha256
    ).hexdigest()


def verify_stream_token(call_sid: str, token: str, secret: str) -> bool:
    return hmac.compare_digest(create_stream_token(call_sid, secret), token)
