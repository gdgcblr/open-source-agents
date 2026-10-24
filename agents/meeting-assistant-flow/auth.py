"""Separate Google identity and read-only Calendar consent flows."""

import json
from pathlib import Path
import secrets
from urllib.parse import urlparse

from google.auth.transport.requests import Request
from google.oauth2.id_token import verify_oauth2_token
from google_auth_oauthlib.flow import Flow

LOGIN_SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email"]
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events.freebusy"
WRITE_SCOPE = "https://www.googleapis.com/auth/calendar.events.owned"


def client_configuration(path: str, redirect_uri: str) -> dict:
    """Fail with a safe message, never the contents of a credential file."""
    try:
        config = json.loads(Path(path).read_text())
        web = config["web"]
        if not all(isinstance(web.get(key), str) and web[key]
                   for key in ("client_id", "client_secret", "auth_uri", "token_uri")):
            raise ValueError
        if web["auth_uri"] != "https://accounts.google.com/o/oauth2/auth":
            raise ValueError
        if web["token_uri"] != "https://oauth2.googleapis.com/token":
            raise ValueError
        if redirect_uri not in web.get("redirect_uris", []):
            raise ValueError
        parsed = urlparse(redirect_uri)
        local_http = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
        if not (parsed.scheme == "https" or local_http) or parsed.path != "/oauth/callback":
            raise ValueError
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError("Configure a Google Web application client and the exact callback URL. See README.md.") from None
    return config


def google_flow(config: dict, redirect_uri: str, state=None, verifier=None, scopes=None):
    return Flow.from_client_config(config, scopes=scopes or LOGIN_SCOPES, redirect_uri=redirect_uri,
                                   state=state, code_verifier=verifier,
                                   autogenerate_code_verifier=verifier is None)


def authorization_request(config: dict, redirect_uri: str) -> dict:
    flow = google_flow(config, redirect_uri)
    nonce = secrets.token_urlsafe(32)
    url, state = flow.authorization_url(access_type="online", prompt="select_account", nonce=nonce)
    return {"url": url, "state": state, "nonce": nonce, "verifier": flow.code_verifier}


def exchange_identity(config: dict, redirect_uri: str, pending: dict, code: str) -> dict:
    flow = google_flow(config, redirect_uri, pending["state"], pending["verifier"])
    flow.fetch_token(code=code, timeout=15)
    return verified_identity(flow, config, pending["nonce"])


def calendar_authorization_request(config: dict, redirect_uri: str, email: str, write=False) -> dict:
    scopes = [*LOGIN_SCOPES, CALENDAR_SCOPE] + ([WRITE_SCOPE] if write else [])
    flow = google_flow(config, redirect_uri, scopes=scopes)
    nonce = secrets.token_urlsafe(32)
    url, state = flow.authorization_url(access_type="offline", prompt="consent select_account",
                                         nonce=nonce, login_hint=email)
    return {"url": url, "state": state, "nonce": nonce, "verifier": flow.code_verifier}


def exchange_calendar(config: dict, redirect_uri: str, pending: dict, code: str):
    required = [CALENDAR_SCOPE] + ([WRITE_SCOPE] if pending.get("intent") == "calendar_write" else [])
    flow = google_flow(config, redirect_uri, pending["state"], pending["verifier"],
                       scopes=[*LOGIN_SCOPES, *required])
    flow.fetch_token(code=code, timeout=15)
    identity = verified_identity(flow, config, pending["nonce"])
    credentials = flow.credentials
    # has_scopes() checks requested scopes, so inspect the actual grant when provided.
    granted = credentials.granted_scopes if credentials.granted_scopes is not None else credentials.scopes
    if isinstance(granted, str):
        granted = granted.split()
    if not set(required).issubset(set(granted or [])):
        raise ValueError("Required Calendar permissions were not granted.")
    if not credentials.refresh_token:
        raise ValueError("Reconnect Calendar and grant access to save this connection.")
    return identity, credentials


def verified_identity(flow, config: dict, nonce: str) -> dict:
    raw_token = flow.oauth2session.token.get("id_token")
    if not raw_token:
        raise ValueError("Google did not return a verified identity.")

    # google-auth checks the signature, expiry, audience, and Google's issuer.
    def bounded_request(*args, **kwargs):
        kwargs["timeout"] = 15
        return Request()(*args, **kwargs)

    claims = verify_oauth2_token(raw_token, bounded_request, audience=config["web"]["client_id"])
    received_nonce = claims.get("nonce")
    if not isinstance(received_nonce, str) or not secrets.compare_digest(received_nonce, nonce):
        raise ValueError("Google login could not be verified. Please try again.")
    if claims.get("email_verified") is not True:
        raise ValueError("A verified Google email address is required.")
    subject, email = claims.get("sub"), claims.get("email")
    if not isinstance(subject, str) or not 1 <= len(subject) <= 255:
        raise ValueError("Google returned an invalid account identifier.")
    if not isinstance(email, str) or "@" not in email or len(email) > 254:
        raise ValueError("Google returned an invalid email address.")
    return {"google_sub": subject, "email": email}
