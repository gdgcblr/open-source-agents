import hashlib
import json
import secrets
import sqlite3
import os
from contextlib import contextmanager

def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

class Store:
    def __init__(self, path):
        self.path = str(path)
        # Create a private database before SQLite opens it; do not widen existing permissions.
        descriptor=os.open(self.path,os.O_CREAT|os.O_RDWR,0o600)
        os.close(descriptor)
        if os.name != "nt":
            os.chmod(self.path,0o600)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS events(name TEXT PRIMARY KEY, spots TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS withdrawals(event TEXT NOT NULL, id TEXT NOT NULL,
                  PRIMARY KEY(event,id));
                CREATE TABLE IF NOT EXISTS people(
                  event TEXT NOT NULL REFERENCES events(name) ON DELETE CASCADE,
                  id TEXT NOT NULL, name TEXT NOT NULL, offers TEXT NOT NULL, needs TEXT NOT NULL,
                  interests TEXT NOT NULL, project TEXT NOT NULL, window TEXT NOT NULL,
                  token_hash TEXT NOT NULL, spot TEXT NOT NULL DEFAULT '',
                  until_ts REAL NOT NULL DEFAULT 0, checked_at REAL NOT NULL DEFAULT 0,
                  PRIMARY KEY(event,id));
                CREATE TABLE IF NOT EXISTS met(event TEXT NOT NULL, viewer TEXT NOT NULL,
                  target TEXT NOT NULL, PRIMARY KEY(event,viewer,target),
                  FOREIGN KEY(event,viewer) REFERENCES people(event,id) ON DELETE CASCADE,
                  FOREIGN KEY(event,target) REFERENCES people(event,id) ON DELETE CASCADE);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA secure_delete=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def import_event(self, event, spots, profiles, demo=False):
        credentials = []
        with self.connect() as db:
            db.execute("INSERT INTO events VALUES(?,?) ON CONFLICT(name) DO UPDATE SET spots=excluded.spots", (event, json.dumps(spots)))
            withdrawn = {r[0] for r in db.execute("SELECT id FROM withdrawals WHERE event=?", (event,))}
            profiles = [p for p in profiles if p["id"] not in withdrawn]
            keep = {p["id"] for p in profiles}
            for row in db.execute("SELECT id FROM people WHERE event=?", (event,)).fetchall():
                if row["id"] not in keep:
                    db.execute("DELETE FROM people WHERE event=? AND id=?", (event, row["id"]))
            for p in profiles:
                old = db.execute("SELECT token_hash,name FROM people WHERE event=? AND id=?", (event, p["id"])).fetchone()
                if old and old["name"] != p["name"]:
                    # An ID accidentally reassigned to another person must not inherit
                    # the old token, location or meeting history. Name corrections
                    # intentionally require distributing a new token as well.
                    db.execute("DELETE FROM people WHERE event=? AND id=?",(event,p["id"]))
                    old=None
                token = f"demo-{p['id']}" if demo else secrets.token_urlsafe(24)
                if not old:
                    credentials.append({"id": p["id"], "name": p["name"], "token": token})
                db.execute('''INSERT INTO people(event,id,name,offers,needs,interests,project,window,token_hash)
                    VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(event,id) DO UPDATE SET
                    name=excluded.name, offers=excluded.offers, needs=excluded.needs,
                    interests=excluded.interests, project=excluded.project, window=excluded.window''',
                    (event, p["id"], p["name"], p["offers"], p["needs"], p["interests"], p["project"], p["window"], old[0] if old else digest(token)))
            # A changed venue configuration invalidates outdated spot names.
            for row in db.execute("SELECT id,spot FROM people WHERE event=?", (event,)).fetchall():
                if row["spot"] not in spots:
                    db.execute("UPDATE people SET spot='',until_ts=0,checked_at=0 WHERE event=? AND id=?", (event,row["id"]))
        return credentials, len(profiles)

    def people(self, event):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM people WHERE event=? ORDER BY id", (event,))]

    def authenticate(self, event, token):
        with self.connect() as db:
            row = db.execute("SELECT * FROM people WHERE event=? AND token_hash=?", (event, digest(token))).fetchone()
            return dict(row) if row else None
