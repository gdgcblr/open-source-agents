"""Model-agnostic SQLite store: result cache, facts, call log, feeds, intel.

Nothing here is keyed by model name, so swapping a tier's model keeps every cached verdict.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from rce_sentinel.memory.trust import VERIFIED, Signer

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

SCHEMA = """
CREATE TABLE IF NOT EXISTS result_cache (
  key TEXT PRIMARY KEY, context_hash TEXT, verdict_json TEXT, model_used TEXT, tier TEXT,
  rules_version TEXT, cve_db_version TEXT, prompt_version TEXT, created_at REAL,
  trust INTEGER DEFAULT 0, sig TEXT);
CREATE TABLE IF NOT EXISTS facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, context_hash TEXT, file TEXT, sink TEXT,
  rule_id TEXT, finding_json TEXT, verdict TEXT, reason TEXT, evidence_json TEXT,
  model_used TEXT, rules_version TEXT, cve_db_version TEXT, commit_sha TEXT,
  invalidated_by TEXT, created_at REAL, repo_id TEXT, trust INTEGER DEFAULT 0, sig TEXT);
CREATE INDEX IF NOT EXISTS facts_sink ON facts(file, sink);
CREATE TABLE IF NOT EXISTS a2a_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, seq INTEGER, sender TEXT,
  recipient TEXT, kind TEXT, trust INTEGER, payload_hash TEXT, prev TEXT, sig TEXT,
  ts REAL);
CREATE TABLE IF NOT EXISTS dep_verdicts (
  ecosystem TEXT, name TEXT, version TEXT, status TEXT, advisories TEXT,
  cve_db_version TEXT, updated_at REAL, PRIMARY KEY (ecosystem, name, version));
CREATE TABLE IF NOT EXISTS llm_calls (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, task_type TEXT, tier TEXT,
  model TEXT, family TEXT, outcome TEXT, confidence REAL, tokens_in INTEGER,
  tokens_out INTEGER, cached_tokens INTEGER, cost REAL, baseline_cost REAL,
  latency_ms REAL, caveman INTEGER, shadow INTEGER DEFAULT 0, final_agree INTEGER,
  simulated INTEGER DEFAULT 0, ts REAL);
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, mode TEXT, started REAL, duration REAL, degraded TEXT,
  findings INTEGER, blocked INTEGER, units INTEGER, cache_hits INTEGER,
  prerouted INTEGER, baseline_units INTEGER, baseline_tokens INTEGER, baseline_cost REAL,
  judged INTEGER);
CREATE TABLE IF NOT EXISTS osv_queries (
  key TEXT PRIMARY KEY, vuln_ids TEXT, fetched_at REAL);
CREATE TABLE IF NOT EXISTS vulns (id TEXT PRIMARY KEY, modified TEXT, pkgs TEXT, json TEXT);
CREATE TABLE IF NOT EXISTS kev (cve TEXT PRIMARY KEY, json TEXT, catalog_version TEXT,
  simulated INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS epss (cve TEXT PRIMARY KEY, score REAL, fetched_at REAL);
CREATE TABLE IF NOT EXISTS intel_items (
  content_hash TEXT PRIMARY KEY, source TEXT, url TEXT, cve_ids TEXT, json TEXT,
  status TEXT, first_seen REAL);
CREATE TABLE IF NOT EXISTS prompt_prefix (model TEXT, prefix_hash TEXT, last_used REAL,
  PRIMARY KEY (model, prefix_hash));
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


class Store:
    def __init__(self, path: Path | str, signer: Signer | None = None):
        self.path = str(path)
        self.signer = signer or Signer.load()
        self.rejected_rows = 0  # rows ignored for a bad or missing signature
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._ensure_columns()
        self.conn.commit()

    def _ensure_columns(self) -> None:
        """Add trust/signature columns to a database created before they existed."""
        wanted = {"result_cache": {"trust": "INTEGER DEFAULT 0", "sig": "TEXT"},
                  "facts": {"repo_id": "TEXT", "trust": "INTEGER DEFAULT 0", "sig": "TEXT"}}
        for table, cols in wanted.items():
            have = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            for col, decl in cols.items():
                if col not in have:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")

    def close(self) -> None:
        self.conn.close()

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            cur = self.conn.execute(sql, params)
            rows = cur.fetchall()
            self.conn.commit()
            return rows

    # --- meta ----------------------------------------------------------------
    def get_meta(self, k: str, default: str = "") -> str:
        rows = self.execute("SELECT v FROM meta WHERE k=?", (k,))
        return rows[0]["v"] if rows else default

    def set_meta(self, k: str, v: str) -> None:
        self.execute("INSERT OR REPLACE INTO meta(k, v) VALUES (?, ?)", (k, v))

    # --- result cache --------------------------------------------------------
    def _cache_sig(self, key: str, verdict_json: str, trust: int, v: dict[str, str]) -> str:
        return self.signer.sign("cache", key, verdict_json, trust, v["rules"], v["cve_db"],
                                v["prompt"])

    def cache_get(self, key: str) -> dict[str, Any] | None:
        """A verdict comes back only if its signature checks out, and a "safe" verdict
        only if it was cross-family verified."""
        rows = self.execute("SELECT * FROM result_cache WHERE key=?", (key,))
        if not rows:
            return None
        row = dict(rows[0])
        versions = {"rules": row["rules_version"], "cve_db": row["cve_db_version"],
                    "prompt": row["prompt_version"]}
        trust = row.get("trust") or 0
        if not self.signer.verify(row.get("sig"), "cache", key, row["verdict_json"], trust,
                                  versions["rules"], versions["cve_db"], versions["prompt"]):
            self.rejected_rows += 1
            return None
        if '"verdict": "safe"' in row["verdict_json"] and trust < VERIFIED:
            self.rejected_rows += 1
            return None
        return row

    def cache_put(self, key: str, context_hash: str, verdict: dict[str, Any], model: str,
                  tier: str, versions: dict[str, str], trust: int = 0) -> None:
        blob = json.dumps(verdict)
        self.execute(
            "INSERT OR REPLACE INTO result_cache VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (key, context_hash, blob, model, tier, versions["rules"], versions["cve_db"],
             versions["prompt"], time.time(), trust,
             self._cache_sig(key, blob, trust, versions)),
        )

    def cache_clear(self) -> int:
        n = self.execute("SELECT COUNT(*) AS n FROM result_cache")[0]["n"]
        self.execute("DELETE FROM result_cache")
        return int(n)

    # --- facts (cross-commit memory) ----------------------------------------
    def _fact_fields(self, r: dict[str, Any]) -> tuple[object, ...]:
        return ("fact", r.get("repo_id"), r.get("file"), r.get("sink"), r.get("rule_id"),
                r.get("verdict"), r.get("reason"), r.get("trust"), r.get("model_used"),
                r.get("commit_sha"))

    def add_fact(self, row: dict[str, Any], *, repo_id: str, trust: int) -> None:
        row = {**row, "repo_id": repo_id, "trust": trust}
        row["sig"] = self.signer.sign(*self._fact_fields(row))
        cols = ",".join(row)
        marks = ",".join("?" for _ in row)
        self.execute(f"INSERT INTO facts({cols}) VALUES ({marks})", tuple(row.values()))

    def prior_facts(self, file: str, sink: str, *, repo_id: str, limit: int = 3,
                    min_trust: int = VERIFIED) -> list[dict[str, Any]]:
        """Earlier reviews of this sink: same repo, validly signed, cross-family verified.
        `reason` is model text, so it is stripped and shortened before anyone sees it."""
        rows = self.execute(
            "SELECT * FROM facts WHERE file=? AND sink=? AND repo_id=? AND invalidated_by "
            "IS NULL ORDER BY id DESC LIMIT 20", (file, sink, repo_id))
        out = []
        for r in rows:
            d = dict(r)
            if not self.signer.verify(d.get("sig"), *self._fact_fields(d)):
                self.rejected_rows += 1
                continue
            if (d.get("trust") or 0) < min_trust:
                continue
            d["reason"] = " ".join(_CTRL.sub("", d.get("reason") or "").split())[:160]
            out.append({k: d[k] for k in ("verdict", "reason", "model_used", "commit_sha",
                                          "created_at")})
            if len(out) >= limit:
                break
        return out

    # --- call log ------------------------------------------------------------
    def log_call(self, row: dict[str, Any]) -> int:
        row = {**row, "ts": time.time()}
        cols = ",".join(row)
        marks = ",".join("?" for _ in row)
        with self._lock:
            cur = self.conn.execute(f"INSERT INTO llm_calls({cols}) VALUES ({marks})",
                                    tuple(row.values()))
            self.conn.commit()
            return int(cur.lastrowid or 0)

    def mark_agreement(self, row_ids: list[int], agree: bool) -> None:
        for rid in row_ids:
            self.execute("UPDATE llm_calls SET final_agree=? WHERE id=?", (int(agree), rid))
