"""Persistence for evaluation records and published dashboard data.

A *record* is the expensive part of judging one PR (static analysis + LLM review), keyed by the PR's
head commit. A PR is only re-evaluated when that commit, the PR description or the judge version
changes. Publishing turns all records into dashboard data (cohort comparisons are recomputed then).

- LocalStore: JSON files. Records in <cache>/records, dashboard data in <out>/results.json + <out>/pr/<id>.json
- FirestoreStore: collections `records`, `submissions`, `details` and the doc `meta/index` (pip install ".[firebase]")
"""

from __future__ import annotations

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
SAFE_ID = re.compile(r"[^A-Za-z0-9._-]")


def _safe(sid: str) -> str:
    return SAFE_ID.sub("_", sid)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


class Store(ABC):
    name = "store"

    @abstractmethod
    def load_records(self) -> dict[str, dict]: ...

    @abstractmethod
    def save_record(self, record: dict) -> None: ...

    @abstractmethod
    def publish(self, index: dict, details: dict[str, dict]) -> str: ...


class LocalStore(Store):
    name = "local"

    def __init__(self, records_dir: Path, out_dir: Path):
        self.records_dir, self.out_dir = records_dir, out_dir

    def load_records(self) -> dict[str, dict]:
        out = {}
        for p in sorted(self.records_dir.glob("*.json")):
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
                out[rec["id"]] = rec
            except (json.JSONDecodeError, KeyError) as exc:
                log.warning("skipping unreadable record %s: %s", p, exc)
        return out

    def save_record(self, record: dict) -> None:
        _write_json(self.records_dir / f"{_safe(record['id'])}.json", record)

    def publish(self, index: dict, details: dict[str, dict]) -> str:
        pr_dir = self.out_dir / "pr"
        keep = {f"{_safe(i)}.json" for i in details}
        if pr_dir.exists():
            for old in pr_dir.glob("*.json"):
                if old.name not in keep:
                    old.unlink()
        for sid, detail in details.items():
            _write_json(pr_dir / f"{_safe(sid)}.json", detail)
        _write_json(self.out_dir / "results.json", index)
        return str(self.out_dir / "results.json")


def firestore_safe(value: Any) -> Any:
    """Firestore can't store arrays directly inside arrays; wrap inner lists in maps."""
    if isinstance(value, dict):
        return {str(k): firestore_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [{"items": firestore_safe(v)} if isinstance(v, (list, tuple)) else firestore_safe(v) for v in value]
    return value


class FirestoreStore(Store):
    name = "firestore"

    def __init__(self, project_id: str | None = None):
        try:
            import firebase_admin
            from firebase_admin import credentials, firestore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError('Firestore support needs: pip install -e ".[firebase]"') from exc
        project_id = project_id or os.getenv("FIREBASE_PROJECT_ID")
        if not firebase_admin._apps:
            cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            cred = credentials.Certificate(cred_path) if cred_path else credentials.ApplicationDefault()
            firebase_admin.initialize_app(cred, {"projectId": project_id} if project_id else None)
        self.db = firestore.client()

    def load_records(self) -> dict[str, dict]:
        return {doc.id: doc.to_dict() for doc in self.db.collection("records").stream()}

    def save_record(self, record: dict) -> None:
        self.db.collection("records").document(_safe(record["id"])).set(firestore_safe(record))

    def publish(self, index: dict, details: dict[str, dict]) -> str:
        batch = self.db.batch()
        for n, (sid, detail) in enumerate(details.items(), 1):
            batch.set(self.db.collection("details").document(_safe(sid)), firestore_safe(detail))
            if n % 200 == 0:  # Firestore batches are limited to 500 writes
                batch.commit()
                batch = self.db.batch()
        for summary in index["submissions"]:
            batch.set(self.db.collection("submissions").document(_safe(summary["id"])), firestore_safe(summary))
        batch.set(self.db.collection("meta").document("index"), firestore_safe(index))
        batch.commit()
        return f"firestore://{self.db.project}/meta/index"


def from_env(kind: str | None, records_dir: Path, out_dir: Path) -> Store:
    kind = (kind or os.getenv("JUDGE_STORE") or "local").lower()
    if kind == "firestore":
        return FirestoreStore()
    if kind != "local":
        raise ValueError(f"unknown store {kind!r} (use local or firestore)")
    return LocalStore(records_dir, out_dir)
