import json
import re
import secrets
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse

import keyring
import requests

LINKEDIN_SERVICE = "gdg-event-marketing"
LINKEDIN_USERNAME = "linkedin"
LINKEDIN_AUTHORIZATION_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
LINKEDIN_POSTS_URL = "https://api.linkedin.com/rest/posts"
LINKEDIN_SCOPES = ("openid", "profile", "w_member_social")
LOCAL_CALLBACK_HOST = "127.0.0.1"
LOCAL_CALLBACK_PORT = 8765


@dataclass(frozen=True)
class LinkedInConnection:
    access_token: str
    person_id: str
    name: str
    expires_at: int


def build_linkedin_authorization_url(
    client_id: str, redirect_uri: str, state: str
) -> str:
    if not client_id.strip():
        raise ValueError("Set LINKEDIN_CLIENT_ID in your local .env file.")
    parsed = urlparse(redirect_uri)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.path != "/callback"
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ValueError(
            "LINKEDIN_REDIRECT_URI must be your registered HTTPS callback URL "
            "ending in /callback."
        )
    if not state:
        raise ValueError("OAuth state must not be empty.")
    return LINKEDIN_AUTHORIZATION_URL + "?" + urlencode(
        {
            "response_type": "code",
            "client_id": client_id.strip(),
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": " ".join(LINKEDIN_SCOPES),
        }
    )


def authorize_linkedin(
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    timeout: int = 180,
    local_callback_port: int = LOCAL_CALLBACK_PORT,
) -> LinkedInConnection:
    if not client_secret.strip():
        raise ValueError("Set LINKEDIN_CLIENT_SECRET in your local .env file.")
    state = secrets.token_urlsafe(32)
    authorization_url = build_linkedin_authorization_url(
        client_id, redirect_uri, state
    )
    callback_result = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            request_url = urlparse(self.path)
            if request_url.path != "/callback":
                self._respond(404, "Not found.")
                return
            query = parse_qs(request_url.query)
            returned_state = query.get("state", [""])[0]
            if not secrets.compare_digest(returned_state, state):
                callback_result["error"] = "LinkedIn authorization state did not match."
                self._respond(400, "Authorization failed. Return to the app and try again.")
                return
            if query.get("error"):
                callback_result["error"] = "LinkedIn authorization was not granted."
                self._respond(400, "Authorization was not granted. You can close this tab.")
                return
            code = query.get("code", [""])[0]
            if not code:
                callback_result["error"] = "LinkedIn did not return an authorization code."
                self._respond(400, "Authorization failed. Return to the app and try again.")
                return
            callback_result["code"] = code
            self._respond(200, "LinkedIn connected. You can close this tab and return to the app.")

        def _respond(self, status: int, message: str) -> None:
            body = message.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *args) -> None:
            return

    server = HTTPServer((LOCAL_CALLBACK_HOST, local_callback_port), CallbackHandler)
    server.timeout = 0.5
    try:
        if not webbrowser.open(authorization_url):
            raise RuntimeError("Could not open a browser for LinkedIn authorization.")
        deadline = time.monotonic() + timeout
        while not callback_result and time.monotonic() < deadline:
            server.handle_request()
        if "error" in callback_result:
            raise RuntimeError(callback_result["error"])
        if "code" not in callback_result:
            raise RuntimeError("LinkedIn authorization timed out.")
    finally:
        server.server_close()

    token_response = requests.post(
        LINKEDIN_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": callback_result["code"],
            "redirect_uri": redirect_uri,
            "client_id": client_id.strip(),
            "client_secret": client_secret.strip(),
        },
        timeout=30,
    )
    token_response.raise_for_status()
    token_data = token_response.json()
    access_token = token_data.get("access_token")
    expires_in = token_data.get("expires_in")
    if not isinstance(access_token, str) or not access_token:
        raise RuntimeError("LinkedIn did not return an access token.")
    if not isinstance(expires_in, int) or expires_in <= 0:
        raise RuntimeError("LinkedIn returned an invalid access-token lifetime.")

    profile_response = requests.get(
        LINKEDIN_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    profile_response.raise_for_status()
    profile = profile_response.json()
    person_id = profile.get("sub")
    if not isinstance(person_id, str) or not person_id:
        raise RuntimeError("LinkedIn did not return the authorized member profile.")
    name = profile.get("name")
    if not isinstance(name, str) or not name:
        name = "LinkedIn member"

    connection = LinkedInConnection(
        access_token=access_token,
        person_id=person_id,
        name=name,
        expires_at=int(time.time()) + expires_in,
    )
    save_linkedin_connection(connection)
    return connection


def save_linkedin_connection(connection: LinkedInConnection) -> None:
    keyring.set_password(
        LINKEDIN_SERVICE,
        LINKEDIN_USERNAME,
        json.dumps(
            {
                "access_token": connection.access_token,
                "person_id": connection.person_id,
                "name": connection.name,
                "expires_at": connection.expires_at,
            }
        ),
    )


def get_linkedin_connection() -> Optional[LinkedInConnection]:
    stored = keyring.get_password(LINKEDIN_SERVICE, LINKEDIN_USERNAME)
    if stored is None:
        return None
    try:
        data = json.loads(stored)
    except json.JSONDecodeError as exc:
        raise ValueError("The saved LinkedIn connection is invalid; reconnect it.") from exc
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("access_token"), str)
        or not isinstance(data.get("person_id"), str)
        or not isinstance(data.get("name"), str)
        or not isinstance(data.get("expires_at"), int)
    ):
        raise ValueError("The saved LinkedIn connection is invalid; reconnect it.")
    if data["expires_at"] <= int(time.time()):
        keyring.delete_password(LINKEDIN_SERVICE, LINKEDIN_USERNAME)
        return None
    return LinkedInConnection(**data)


def disconnect_linkedin() -> bool:
    if keyring.get_password(LINKEDIN_SERVICE, LINKEDIN_USERNAME) is None:
        return False
    keyring.delete_password(LINKEDIN_SERVICE, LINKEDIN_USERNAME)
    return True


def publish_linkedin_post(draft: str, api_version: str) -> str:
    text = draft.strip()
    if not text:
        raise ValueError("The LinkedIn draft is empty.")
    if not re.fullmatch(r"\d{6}", api_version):
        raise ValueError("LINKEDIN_API_VERSION must use YYYYMM format.")
    connection = get_linkedin_connection()
    if connection is None:
        raise ValueError("Connect your LinkedIn account before publishing.")
    response = requests.post(
        LINKEDIN_POSTS_URL,
        headers={
            "Authorization": f"Bearer {connection.access_token}",
            "Content-Type": "application/json",
            "LinkedIn-Version": api_version,
            "X-Restli-Protocol-Version": "2.0.0",
        },
        json={
            "author": f"urn:li:person:{connection.person_id}",
            "commentary": text,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.headers.get("x-restli-id", "Post published successfully.")
