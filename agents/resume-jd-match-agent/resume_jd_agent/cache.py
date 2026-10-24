"""On-disk cache of finished reports, keyed by resume + JD content + model.

Asking about the same resume and JD again returns the saved report with zero
Gemini requests, and identical inputs always give identical reports.

Reports contain resume details, so the cache lives in the git-ignored
resume_jd_agent/.cache/ folder, with restricted file permissions (0600) so
only the current user can read them. Old entries are automatically pruned.
Set RESUME_JD_CACHE=off to disable it, and delete the folder to clear it.
"""

import hashlib
import json
import logging
import os
import time

from . import config

logger = logging.getLogger("resume_jd_agent.cache")

# Bump when the prompt or report format changes, so old reports are not reused.
CACHE_VERSION = config.CACHE_VERSION
CACHE_DIR = config.CACHE_DIR
CACHE_ENV = config.CACHE_ENV
MAX_AGE_SECONDS = config.MAX_AGE_SECONDS


def enabled() -> bool:
    return os.getenv(CACHE_ENV, "on").lower() not in ("off", "0", "false", "no")


def normalise(text: str) -> str:
    return " ".join(text.split())


def key_for(resume_text: str, jd_text: str, model: str = config.MODEL_NAME) -> str:
    """Stable key for one resume + JD pair and model (whitespace-insensitive)."""
    payload = json.dumps([CACHE_VERSION, model or "", normalise(resume_text), normalise(jd_text)])
    return hashlib.sha256(payload.encode()).hexdigest()


def _path(key: str) -> str:
    return os.path.join(CACHE_DIR, f"{key}.json")


def prune(max_age_seconds: int = MAX_AGE_SECONDS) -> int:
    """Removes cached reports older than max_age_seconds and orphaned .tmp files.

    Returns the count of pruned files.
    """
    if not os.path.isdir(CACHE_DIR):
        return 0
    pruned = 0
    now = time.time()
    try:
        for entry in os.scandir(CACHE_DIR):
            if not entry.is_file():
                continue
            should_remove = False
            try:
                mtime = entry.stat().st_mtime
                if entry.name.endswith(".tmp") and (now - mtime > 3600):
                    should_remove = True
                elif entry.name.endswith(".json"):
                    if now - mtime > max_age_seconds:
                        should_remove = True
                    else:
                        with open(entry.path, encoding="utf-8") as f:
                            data = json.load(f)
                        if now - data.get("created", 0) > max_age_seconds:
                            should_remove = True
            except (OSError, ValueError):
                should_remove = True

            if should_remove:
                try:
                    os.remove(entry.path)
                    pruned += 1
                except OSError:
                    pass
    except OSError:
        pass
    if pruned:
        logger.info("Pruned %d expired report cache file(s)", pruned)
    return pruned


def get(key: str) -> str | None:
    """Returns the cached report, or None if missing, expired or disabled."""
    if not enabled() or not key:
        return None
    path = _path(key)
    try:
        with open(path, encoding="utf-8") as f:
            entry = json.load(f)
    except (OSError, ValueError):
        return None
    if time.time() - entry.get("created", 0) > MAX_AGE_SECONDS:
        try:
            os.remove(path)
        except OSError:
            pass
        return None
    logger.info("Report cache hit (key=%s)", key[:12])
    return entry.get("report")


def put(key: str, report: str) -> None:
    """Saves a report with restricted permissions (0600). Failures are ignored."""
    if not enabled() or not key:
        return
    try:
        os.makedirs(CACHE_DIR, mode=0o700, exist_ok=True)
        try:
            os.chmod(CACHE_DIR, 0o700)
        except OSError:
            pass
        tmp = _path(key) + ".tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(tmp, flags, 0o600)
        with open(fd, "w", encoding="utf-8") as f:
            json.dump({"created": time.time(), "report": report}, f)
        os.replace(tmp, _path(key))
        try:
            os.chmod(_path(key), 0o600)
        except OSError:
            pass
        logger.info("Report cached successfully (key=%s)", key[:12])
        prune()
    except OSError as exc:
        logger.warning("Failed to save report to cache: %s", exc)
