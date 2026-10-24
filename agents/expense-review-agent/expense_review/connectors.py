"""Read-only Gmail OAuth and personal Keep Takeout import."""

import base64
import hashlib
import json
import os
from html.parser import HTMLParser
from pathlib import Path

from .models import SourceNote


GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
DEFAULT_QUERY = "newer_than:45d (receipt OR debited OR credited OR paid OR transaction OR lent OR borrowed)"
DATA_HOME = Path(os.environ.get("EXPENSE_DATA_DIR", Path.home() / ".local/share/expense-review"))


def authorize_gmail(credentials_path: Path, token_path: Path) -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), GMAIL_SCOPES)
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    save_token(token_path, credentials.to_json())


def save_token(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as token_file:
        token_file.write(content)
    path.chmod(0o600)


class PlainHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fragments: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.fragments.append(data)


def message_text(payload: dict) -> str:
    plain: list[str] = []
    html: list[str] = []

    def visit(part: dict) -> None:
        if part.get("filename"):
            return
        data = part.get("body", {}).get("data")
        if data:
            text = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
            if part.get("mimeType") == "text/plain":
                plain.append(text)
            elif part.get("mimeType") == "text/html":
                parser = PlainHTML()
                parser.feed(text)
                html.append(" ".join(parser.fragments))
        for child in part.get("parts", []):
            visit(child)

    visit(payload)
    return "\n".join(plain or html).strip()


def fetch_gmail(token_path: Path, query: str = DEFAULT_QUERY, limit: int = 20) -> list[SourceNote]:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    import httplib2
    from google_auth_httplib2 import AuthorizedHttp

    if not 1 <= limit <= 50:
        raise ValueError("Gmail fetch limit must be 1-50")
    if not token_path.is_file():
        raise ValueError("Gmail is not connected. Run expense-review auth-gmail locally first.")
    credentials = Credentials.from_authorized_user_file(str(token_path), GMAIL_SCOPES)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        save_token(token_path, credentials.to_json())
    if not credentials.valid:
        raise ValueError("Gmail authorization expired. Run expense-review auth-gmail again.")
    service = build("gmail", "v1", http=AuthorizedHttp(credentials, http=httplib2.Http(timeout=30)),
                    cache_discovery=False)
    profile = service.users().getProfile(userId="me").execute()
    account = hashlib.sha256(profile["emailAddress"].encode()).hexdigest()[:16]
    notes = []
    page_token = None
    while len(notes) < limit:
        result = service.users().messages().list(userId="me", q=query, maxResults=limit - len(notes),
                                                pageToken=page_token).execute()
        for item in result.get("messages", []):
            message = service.users().messages().get(userId="me", id=item["id"], format="full").execute()
            payload = message.get("payload", {})
            headers = {header["name"].lower(): header["value"] for header in payload.get("headers", [])}
            text = message_text(payload) or message.get("snippet", "")
            if not text.strip():
                continue
            notes.append(SourceNote(source="gmail", source_id=f"{account}:{item['id']}",
                                    title=headers.get("subject", "Untitled email")[:500],
                                    text=text[:20000],
                                    source_url=f"https://mail.google.com/mail/u/0/#all/{item['id']}"))
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return notes


def import_keep(data: object) -> list[SourceNote]:
    if isinstance(data, dict) and "notes" in data:
        items = data["notes"]
    else:
        items = data if isinstance(data, list) else [data]
    if not isinstance(items, list) or len(items) > 100:
        raise ValueError("Import at most 100 Keep notes at a time")
    notes = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each Keep note must be a JSON object")
        if item.get("isTrashed"):
            continue
        title = str(item.get("title", "Untitled note"))[:500]
        text = item.get("textContent", "")
        if not isinstance(text, str):
            raise ValueError("Keep textContent must be a string")
        checklist = item.get("listContent", [])
        if not isinstance(checklist, list):
            raise ValueError("Keep listContent must be a list")
        text = "\n".join([text] + [str(entry.get("text", "")) for entry in checklist if isinstance(entry, dict)]).strip()
        if not text:
            continue
        identity = str(item.get("id") or item.get("createdTimestampUsec") or
                       hashlib.sha256((title + text).encode()).hexdigest())
        notes.append(SourceNote(source="keep", source_id=identity[:300], title=title, text=text[:20000]))
    return notes


def read_keep(path: Path) -> list[SourceNote]:
    if path.stat().st_size > 4_000_000:
        raise ValueError("Keep JSON file must be at most 4 MB")
    return import_keep(json.loads(path.read_text(encoding="utf-8")))