import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from .catalog import PLACES, SEED_ENTRIES


class Store:
    """Single-user, loopback-only demo repository. No production auth bypass."""
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        (root / "media").mkdir(exist_ok=True)
        self.path = root / "travelogue.sqlite3"
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS entries (
                    id TEXT PRIMARY KEY, country TEXT NOT NULL, place_id TEXT NOT NULL,
                    title TEXT NOT NULL, visited_on TEXT NOT NULL, body TEXT NOT NULL,
                    published INTEGER NOT NULL DEFAULT 0, tags TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS media (
                    id TEXT PRIMARY KEY, entry_id TEXT NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
                    filename TEXT NOT NULL, mime TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS saved_plans (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            ''')
            if not db.execute("SELECT 1 FROM metadata WHERE key='seeded'").fetchone():
                for e in SEED_ENTRIES:
                    db.execute("INSERT INTO entries VALUES (:id,:country,:place_id,:title,:visited_on,:body,:published,:tags)", e)
                db.execute("INSERT INTO metadata VALUES ('seeded','1')")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def entries(self):
        with self.connection() as db:
            result = [dict(r) for r in db.execute("SELECT * FROM entries ORDER BY visited_on DESC, id")]
            for e in result:
                e["published"] = bool(e["published"])
                e["media"] = [dict(r) for r in db.execute("SELECT * FROM media WHERE entry_id=?", (e["id"],))]
        return result

    def entry(self, ident):
        return next((e for e in self.entries() if e["id"] == ident), None)

    def save_entry(self, data, ident=None):
        ident = ident or str(uuid.uuid4())
        values = data.model_dump(mode="json")
        values.update(id=ident, country=PLACES[values["place_id"]]["country"])
        with self.connection() as db:
            db.execute('''INSERT INTO entries VALUES (:id,:country,:place_id,:title,:visited_on,:body,:published,:tags)
                ON CONFLICT(id) DO UPDATE SET country=excluded.country, place_id=excluded.place_id,
                title=excluded.title, visited_on=excluded.visited_on, body=excluded.body,
                published=excluded.published, tags=excluded.tags''', values)
        return self.entry(ident)

    def delete_entry(self, ident):
        with self.connection() as db:
            media = list(db.execute("SELECT id FROM media WHERE entry_id=?", (ident,)))
            db.execute("DELETE FROM entries WHERE id=?", (ident,))
        for row in media:
            (self.root / "media" / row["id"]).unlink(missing_ok=True)

    def put_json(self, table, ident, payload):
        if table not in {"runs", "saved_plans"}:
            raise ValueError("Unknown collection")
        with self.connection() as db:
            db.execute(f"INSERT INTO {table} VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (ident, json.dumps(payload)))

    def get_json(self, table, ident):
        if table not in {"runs", "saved_plans"}:
            raise ValueError("Unknown collection")
        with self.connection() as db:
            row = db.execute(f"SELECT payload FROM {table} WHERE id=?", (ident,)).fetchone()
        return json.loads(row[0]) if row else None

    def saved(self):
        with self.connection() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT payload FROM saved_plans ORDER BY rowid DESC")]
