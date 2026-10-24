"""A small SQLite store. Every read and update includes the browser's owner ID."""

import json
import hashlib
import secrets
import sqlite3
import time
import uuid


class DraftStore:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS drafts (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, version INTEGER NOT NULL,
                status TEXT NOT NULL, data TEXT NOT NULL, updated REAL NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY, google_sub TEXT UNIQUE NOT NULL, email TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS oauth_requests (
                state TEXT PRIMARY KEY, browser TEXT NOT NULL, nonce TEXT NOT NULL,
                verifier TEXT NOT NULL, expires REAL NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS login_sessions (
                token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS calendar_connections (
                user_id TEXT PRIMARY KEY, connected_at REAL NOT NULL)""")
            calendar_columns = {row["name"] for row in db.execute("PRAGMA table_info(calendar_connections)")}
            if "can_write" not in calendar_columns:
                db.execute("ALTER TABLE calendar_connections ADD COLUMN can_write INTEGER NOT NULL DEFAULT 0")
            # Upgrade existing Step 1 databases without removing accounts or sessions.
            columns = {row["name"] for row in db.execute("PRAGMA table_info(oauth_requests)")}
            if "intent" not in columns:
                db.execute("ALTER TABLE oauth_requests ADD COLUMN intent TEXT NOT NULL DEFAULT 'login'")
            if "user_id" not in columns:
                db.execute("ALTER TABLE oauth_requests ADD COLUMN user_id TEXT")

    def save_oauth_request(self, pending, browser, intent="login", user_id=None):
        with self.connect() as db:
            db.execute("DELETE FROM oauth_requests WHERE expires<? OR browser=?", (time.time(), browser))
            db.execute("""INSERT INTO oauth_requests
                (state,browser,nonce,verifier,expires,intent,user_id) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (pending["state"], browser, pending["nonce"], pending["verifier"], time.time() + 600, intent, user_id))

    def google_subject(self, user_id):
        with self.connect() as db:
            row = db.execute("SELECT google_sub FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None:
            raise LookupError("Account not found.")
        return row["google_sub"]

    def calendar_connected(self, user_id):
        with self.connect() as db:
            return db.execute("SELECT 1 FROM calendar_connections WHERE user_id=?", (user_id,)).fetchone() is not None

    def calendar_writable(self, user_id):
        with self.connect() as db:
            row = db.execute("SELECT can_write FROM calendar_connections WHERE user_id=?", (user_id,)).fetchone()
        return bool(row and row["can_write"])

    def set_calendar_connected(self, user_id, connected, can_write=False):
        with self.connect() as db:
            if connected:
                db.execute("INSERT OR REPLACE INTO calendar_connections (user_id,connected_at,can_write) VALUES (?, ?, ?)",
                           (user_id, time.time(), int(can_write)))
            else:
                db.execute("DELETE FROM calendar_connections WHERE user_id=?", (user_id,))

    def consume_oauth_request(self, state, browser):
        # DELETE RETURNING makes every login attempt single-use, including failures.
        with self.connect() as db:
            row = db.execute("DELETE FROM oauth_requests WHERE state=? AND browser=? RETURNING *",
                             (state, browser)).fetchone()
        if row is None or row["expires"] < time.time():
            raise ValueError("Login expired or could not be verified. Start again.")
        return dict(row)

    def create_login(self, identity):
        with self.connect() as db:
            db.execute("""INSERT INTO users VALUES (?, ?, ?)
                ON CONFLICT(google_sub) DO UPDATE SET email=excluded.email""",
                       (uuid.uuid4().hex, identity["google_sub"], identity["email"]))
            user = db.execute("SELECT id FROM users WHERE google_sub=?", (identity["google_sub"],)).fetchone()
            token = secrets.token_urlsafe(32)
            db.execute("DELETE FROM login_sessions WHERE expires<?", (time.time(),))
            db.execute("INSERT INTO login_sessions VALUES (?, ?, ?)",
                       (self.token_hash(token), user["id"], time.time() + 8 * 3600))
        return token

    @staticmethod
    def token_hash(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def current_user(self, token):
        if not token:
            return None
        with self.connect() as db:
            row = db.execute("""SELECT users.id, users.email FROM users
                JOIN login_sessions ON users.id=login_sessions.user_id
                WHERE token_hash=? AND expires>?""", (self.token_hash(token), time.time())).fetchone()
        return dict(row) if row else None

    def revoke_login(self, token):
        if token:
            with self.connect() as db:
                db.execute("DELETE FROM login_sessions WHERE token_hash=?", (self.token_hash(token),))

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def get(self, draft_id, owner):
        with self.connect() as db:
            row = db.execute("SELECT * FROM drafts WHERE id=? AND owner=?", (draft_id, owner)).fetchone()
        if row is None:
            raise LookupError("Meeting draft not found.")
        result = dict(row)
        result["data"] = json.loads(result["data"])
        result.pop("owner")
        return result

    def list_for_owner(self, owner):
        with self.connect() as db:
            rows = db.execute("SELECT id,status,data FROM drafts WHERE owner=? ORDER BY updated DESC LIMIT 10", (owner,)).fetchall()
        return [{"id": row["id"], "status": row["status"], "title": json.loads(row["data"])["meeting"]["title"]} for row in rows]

    def create(self, owner, data):
        draft_id = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO drafts VALUES (?, ?, 1, 'draft', ?, ?)",
                       (draft_id, owner, json.dumps(data), time.time()))
        return self.get(draft_id, owner)

    def update(self, draft_id, owner, version, data, status="draft"):
        with self.connect() as db:
            changed = db.execute("""UPDATE drafts SET data=?, status=?, version=version+1, updated=?
                WHERE id=? AND owner=? AND version=? AND status IN ('draft','ready')
                AND json_extract(data, '$.attempted') IS NOT 1""",
                (json.dumps(data), status, time.time(), draft_id, owner, version)).rowcount
        if not changed:
            raise ValueError("Draft changed or is locked. Reload it before continuing.")
        return self.get(draft_id, owner)

    def claim(self, draft_id, owner, version):
        with self.connect() as db:
            changed = db.execute("""UPDATE drafts SET status='creating', updated=?
                WHERE id=? AND owner=? AND version=? AND status='ready'""",
                (time.time(), draft_id, owner, version)).rowcount
        if not changed:
            raise ValueError("Meeting changed or creation is already in progress. Reload its status.")

    def finish(self, draft_id, owner, data, status):
        with self.connect() as db:
            db.execute("UPDATE drafts SET data=?, status=?, version=version+1, updated=? WHERE id=? AND owner=?",
                       (json.dumps(data), status, time.time(), draft_id, owner))
        return self.get(draft_id, owner)

    def begin_submission(self, draft_id, owner, version, data):
        """A status check/recovery during the network preflight must cancel this write."""
        with self.connect() as db:
            changed = db.execute("""UPDATE drafts SET data=?, version=version+1, updated=?
                WHERE id=? AND owner=? AND version=? AND status='creating'""",
                (json.dumps(data), time.time(), draft_id, owner, version)).rowcount
        if not changed:
            raise ValueError("Operation changed during availability recheck.")

    def delete(self, draft_id, owner):
        with self.connect() as db:
            changed = db.execute("DELETE FROM drafts WHERE id=? AND owner=? AND status NOT IN ('creating','unknown')",
                                 (draft_id, owner)).rowcount
        if not changed:
            raise ValueError("Draft not found or its calendar operation must be reconciled first.")

    def clear_chats(self, owner):
        """Forget chat content without hiding operations whose outcome is uncertain."""
        with self.connect() as db:
            db.execute("""DELETE FROM drafts WHERE owner=? AND
                (status IN ('created','cancelled') OR
                 (status IN ('draft','ready') AND json_extract(data, '$.attempted') IS NOT 1))""", (owner,))

    def pending_operations(self, owner):
        with self.connect() as db:
            rows = db.execute("""SELECT id FROM drafts WHERE owner=? AND
                (status IN ('creating','unknown') OR (status='ready' AND json_extract(data, '$.attempted')=1))""", (owner,)).fetchall()
        return [row["id"] for row in rows]

    def expire(self):
        with self.connect() as db:
            # Keep uncertain operations until reconciled, so deletion cannot hide a booking.
            db.execute("DELETE FROM drafts WHERE updated<? AND status NOT IN ('creating','unknown')",
                       (time.time() - 7 * 86400,))
