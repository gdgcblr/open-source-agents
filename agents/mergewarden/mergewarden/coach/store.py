"""Persistent coach state in one stdlib sqlite file.

- users:       hashed id only (sha256(phone + salt)), plus the profile the
               student chose to share (language, skills, GitHub handle).
- ledger:      append-only points log. Every row has a reason and an
               evidence link, and a UNIQUE event key so the same event can
               never pay twice. No UPDATE statements touch it; the only
               DELETE is the student's own "delete my data".
- badges:      earned once per user.
- transcript:  the last few redacted turns, so a conversation can resume
               after a restart. Audio is never stored, only its transcript.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import config

POINTS = {
    "report_bug": 5,
    "clarify_issue": 5,
    "fix_plan": 10,
    "pr_opened": 20,
    "pr_merged": 50,
}
BADGES = {
    "first_steps": "🌱 First Steps",
    "polyglot": "🗣️ Polyglot",
    "bug_hunter": "🐞 Bug Hunter",
    "docs_hero": "📚 Docs Hero",
    "merged": "🏆 Merged!",
    "clean_pr": "✅ Clean PR",
}
KEEP_TURNS = 20

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  user_hash TEXT PRIMARY KEY,
  created_at REAL NOT NULL,
  profile TEXT NOT NULL DEFAULT '{}',
  languages TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_hash TEXT NOT NULL,
  event_key TEXT NOT NULL,
  kind TEXT NOT NULL,
  points INTEGER NOT NULL,
  reason TEXT NOT NULL,
  evidence TEXT NOT NULL,
  day TEXT NOT NULL,
  created_at REAL NOT NULL,
  UNIQUE(user_hash, event_key)
);
CREATE TABLE IF NOT EXISTS badges (
  user_hash TEXT NOT NULL,
  badge TEXT NOT NULL,
  created_at REAL NOT NULL,
  PRIMARY KEY (user_hash, badge)
);
CREATE TABLE IF NOT EXISTS transcript (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_hash TEXT NOT NULL,
  role TEXT NOT NULL,
  text TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_hash TEXT NOT NULL,
  pr_url TEXT NOT NULL,
  status TEXT NOT NULL,
  verdict TEXT,
  score INTEGER,
  result TEXT,
  started_at REAL NOT NULL,
  finished_at REAL
);
CREATE TRIGGER IF NOT EXISTS ledger_append_only BEFORE UPDATE ON ledger
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
"""


@dataclass
class Award:
    kind: str
    points: int  # what was actually credited (0 if duplicate or capped)
    duplicate: bool = False
    capped: bool = False
    new_badges: list[str] | None = None


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class Store:
    def __init__(self, path: Path | str | None = None):
        if path is None:
            config.drafts_dir()  # creates DATA_DIR and its protective .gitignore
            path = config.DATA_DIR / "coach.sqlite3"
        self.path = str(path)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)

    # --- users -------------------------------------------------------------

    def get_user(self, uh: str) -> dict | None:
        r = self._db.execute("SELECT * FROM users WHERE user_hash=?", (uh,)).fetchone()
        if not r:
            return None
        return {"user_hash": uh, "created_at": r["created_at"],
                "profile": json.loads(r["profile"]), "languages": json.loads(r["languages"])}

    def ensure_user(self, uh: str) -> tuple[dict, bool]:
        """Returns (user, is_new)."""
        with self._lock, self._db:
            cur = self._db.execute("INSERT OR IGNORE INTO users(user_hash, created_at) VALUES (?, ?)", (uh, time.time()))
        return self.get_user(uh), cur.rowcount == 1

    def update_profile(self, uh: str, **fields) -> dict:
        user, _ = self.ensure_user(uh)
        profile = {**user["profile"], **{k: v for k, v in fields.items() if v not in (None, "")}}
        with self._lock, self._db:
            self._db.execute("UPDATE users SET profile=? WHERE user_hash=?", (json.dumps(profile), uh))
        return profile

    def note_language(self, uh: str, language: str) -> list[str]:
        """Record a language the student used; returns any new badges (Polyglot)."""
        user, _ = self.ensure_user(uh)
        langs = user["languages"]
        lang = (language or "").strip().lower()
        if lang and lang not in langs:
            langs.append(lang)
            with self._lock, self._db:
                self._db.execute("UPDATE users SET languages=? WHERE user_hash=?", (json.dumps(langs), uh))
        return [b for b in ["polyglot"] if len(langs) >= 2 and self.grant_badge(uh, b)]

    def delete_user(self, uh: str) -> None:
        """Right to erasure: the one exception to the append-only ledger."""
        with self._lock, self._db:
            for table in ("users", "ledger", "badges", "transcript", "reviews"):
                self._db.execute(f"DELETE FROM {table} WHERE user_hash=?", (uh,))

    # --- points ------------------------------------------------------------

    def points_today(self, uh: str) -> int:
        r = self._db.execute("SELECT COALESCE(SUM(points),0) FROM ledger WHERE user_hash=? AND day=?",
                             (uh, _today())).fetchone()
        return int(r[0])

    def total(self, uh: str) -> int:
        r = self._db.execute("SELECT COALESCE(SUM(points),0) FROM ledger WHERE user_hash=?", (uh,)).fetchone()
        return int(r[0])

    def handle_owner(self, github: str) -> str | None:
        """The user who registered this GitHub handle, if any (one handle per student)."""
        for r in self._db.execute("SELECT user_hash, profile FROM users").fetchall():
            if (json.loads(r["profile"]).get("github") or "").lower() == github.lower():
                return r["user_hash"]
        return None

    def award(self, uh: str, kind: str, event_key: str, reason: str, evidence: str, tags: tuple[str, ...] = (),
              global_event: bool = False) -> Award:
        """Credit points for one event. Idempotent on (user, event_key); capped per day.

        global_event=True: the event (e.g. a PR) pays only once across ALL users.
        """
        if kind not in POINTS:
            raise ValueError(f"unknown points kind {kind!r}")
        if not evidence:
            raise ValueError("every award needs an evidence link or reference")
        self.ensure_user(uh)
        with self._lock:
            q, args = ("SELECT 1 FROM ledger WHERE event_key=?", (event_key,)) if global_event else \
                ("SELECT 1 FROM ledger WHERE user_hash=? AND event_key=?", (uh, event_key))
            if self._db.execute(q, args).fetchone():
                return Award(kind, 0, duplicate=True)
            room = max(0, config.DAILY_POINT_CAP - self.points_today(uh))
            pts = min(POINTS[kind], room)
            if pts == 0:  # not recorded, so the event can still be claimed tomorrow
                return Award(kind, 0, capped=True)
            with self._db:
                self._db.execute(
                    "INSERT INTO ledger(user_hash,event_key,kind,points,reason,evidence,day,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (uh, event_key, kind, pts, reason[:300], evidence[:500], _today(), time.time()))
        badges = [b for b in self._badges_for(kind, tags) if self.grant_badge(uh, b)]
        return Award(kind, pts, capped=pts < POINTS[kind], new_badges=badges)

    @staticmethod
    def _badges_for(kind: str, tags: tuple[str, ...]) -> list[str]:
        out = ["first_steps"]
        if kind == "report_bug":
            out.append("bug_hunter")
        if kind in ("fix_plan", "pr_opened", "pr_merged") and "docs" in tags:
            out.append("docs_hero")
        if kind == "pr_merged":
            out.append("merged")
        return out

    def ledger(self, uh: str) -> list[dict]:
        rows = self._db.execute("SELECT kind,points,reason,evidence,day FROM ledger WHERE user_hash=? ORDER BY id",
                                (uh,)).fetchall()
        return [dict(r) for r in rows]

    # --- badges ------------------------------------------------------------

    def grant_badge(self, uh: str, badge: str) -> bool:
        """True only the first time the badge is earned."""
        with self._lock, self._db:
            cur = self._db.execute("INSERT OR IGNORE INTO badges(user_hash,badge,created_at) VALUES (?,?,?)",
                                   (uh, badge, time.time()))
        return cur.rowcount == 1

    def badges(self, uh: str) -> list[str]:
        rows = self._db.execute("SELECT badge FROM badges WHERE user_hash=? ORDER BY created_at", (uh,)).fetchall()
        return [r[0] for r in rows]

    # --- leaderboard -------------------------------------------------------

    def leaderboard(self, limit: int = 10) -> list[dict]:
        rows = self._db.execute(
            "SELECT u.user_hash, u.profile, COALESCE(SUM(l.points),0) AS pts FROM users u "
            "JOIN ledger l ON l.user_hash=u.user_hash GROUP BY u.user_hash HAVING pts>0 "
            "ORDER BY pts DESC, MIN(l.created_at) ASC LIMIT ?", (limit,)).fetchall()
        out = []
        for i, r in enumerate(rows, 1):
            out.append({"rank": i, "name": display_name(r["user_hash"], json.loads(r["profile"])),
                        "points": r["pts"], "badges": [BADGES[b] for b in self.badges(r["user_hash"])]})
        return out

    # --- gatekeeper reviews ------------------------------------------------

    def start_review(self, uh: str, pr_url: str) -> int:
        with self._lock, self._db:
            cur = self._db.execute("INSERT INTO reviews(user_hash,pr_url,status,started_at) VALUES (?,?,?,?)",
                                   (uh, pr_url, "running", time.time()))
        return cur.lastrowid

    def finish_review(self, review_id: int, status: str, result: dict) -> None:
        with self._lock, self._db:
            self._db.execute("UPDATE reviews SET status=?, verdict=?, score=?, result=?, finished_at=? WHERE id=?",
                             (status, result.get("verdict"), result.get("score"), json.dumps(result), time.time(),
                              review_id))

    def latest_review(self, uh: str, pr_url: str | None = None) -> dict | None:
        q = "SELECT * FROM reviews WHERE user_hash=?" + (" AND pr_url=?" if pr_url else "") + " ORDER BY id DESC LIMIT 1"
        r = self._db.execute(q, (uh, pr_url) if pr_url else (uh,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["result"] = json.loads(d["result"]) if d["result"] else None
        return d

    def reviews_today(self, uh: str) -> int:
        since = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        return self._db.execute("SELECT COUNT(*) FROM reviews WHERE user_hash=? AND started_at>=?",
                                (uh, since)).fetchone()[0]

    # --- transcript --------------------------------------------------------

    def add_turn(self, uh: str, role: str, text: str) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT INTO transcript(user_hash,role,text,created_at) VALUES (?,?,?,?)",
                             (uh, role, text[:2000], time.time()))
            self._db.execute(
                "DELETE FROM transcript WHERE user_hash=? AND id NOT IN "
                "(SELECT id FROM transcript WHERE user_hash=? ORDER BY id DESC LIMIT ?)", (uh, uh, KEEP_TURNS))

    def recent_turns(self, uh: str, n: int = 8) -> list[dict]:
        rows = self._db.execute("SELECT role,text FROM transcript WHERE user_hash=? ORDER BY id DESC LIMIT ?",
                                (uh, n)).fetchall()
        return [dict(r) for r in reversed(rows)]


def display_name(uh: str, profile: dict) -> str:
    """Public name: the GitHub handle the student registered, else a pseudonym."""
    gh = profile.get("github")
    return f"@{gh}" if gh else f"Coder-{uh[:5]}"
