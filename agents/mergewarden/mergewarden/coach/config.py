"""Every knob of Namma Commit (the Newcomer Coach), read from the environment once."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # agents/mergewarden/


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


MODEL = os.environ.get("GATEKEEPER_COACH_MODEL", "gemini-3.8-flash")
FALLBACK_MODEL = os.environ.get("GATEKEEPER_COACH_FALLBACK_MODEL", "gemini-3.5-flash-lite")
# "github": recommend skill-matched issues from all of GitHub (points still only for REPOS);
# "allowlist": only REPOS and event challenges.
DISCOVERY = os.environ.get("COACH_DISCOVERY", "github").lower()
MIN_STARS = _int("COACH_MIN_STARS", 20)  # ignore tiny/abandoned repos when recommending
REVIEW_MAX_REPO_MB = _int("COACH_REVIEW_MAX_REPO_MB", 200)  # skip MergeWarden reviews of huge repos (clone cost)
EXPLORER_MIN_STARS = _int("COACH_EXPLORER_MIN_STARS", 50)  # verified PR to such a repo earns the Explorer badge
REPOS = [r.strip() for r in os.environ.get("COACH_REPOS", "gdgcblr/open-source-agents").split(",") if r.strip()]
DATA_DIR = Path(os.environ.get("COACH_DATA_DIR", PROJECT_ROOT / ".coach-data")).resolve()
SALT = os.environ.get("COACH_SALT", "")  # set a long random value in production
PORT = _int("COACH_PORT", 8090)
# The web simulator replies in this language only ("auto" = the student's own language, like WhatsApp).
SIMULATOR_LANGUAGE = os.environ.get("COACH_SIMULATOR_LANGUAGE", "English").strip()
SIMULATOR_FORCE_LANGUAGE = None if SIMULATOR_LANGUAGE.lower() in {"", "auto"} else SIMULATOR_LANGUAGE

# Abuse limits
RATE_LIMIT_MSGS = _int("COACH_RATE_LIMIT_MSGS", 20)
RATE_LIMIT_WINDOW_S = _int("COACH_RATE_LIMIT_WINDOW_S", 600)
MAX_AUDIO_BYTES = _int("COACH_MAX_AUDIO_BYTES", 5 * 1024 * 1024)
MAX_AUDIO_SECONDS = _int("COACH_MAX_AUDIO_SECONDS", 120)
MAX_TEXT_CHARS = _int("COACH_MAX_TEXT_CHARS", 2000)
MAX_TURNS_PER_SESSION = _int("COACH_MAX_TURNS_PER_SESSION", 60)
DAILY_POINT_CAP = _int("COACH_DAILY_POINT_CAP", 100)

# Final-step gatekeeper review of the student's PR
REVIEW_USE_LLM = os.environ.get("COACH_REVIEW_USE_LLM", "1").lower() not in {"0", "false", "no"}
REVIEW_TIMEOUT_S = _int("COACH_REVIEW_TIMEOUT_S", 600)
REVIEW_COOLDOWN_S = _int("COACH_REVIEW_COOLDOWN_S", 300)
MAX_REVIEWS_PER_DAY = _int("COACH_MAX_REVIEWS_PER_DAY", 5)
REVIEW_CONCURRENCY = _int("COACH_REVIEW_CONCURRENCY", 2)

# Twilio WhatsApp (optional; the simulator needs none of these)
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "")  # e.g. whatsapp:+14155238886
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")


def drafts_dir() -> Path:
    d = DATA_DIR / "drafts"
    d.mkdir(parents=True, exist_ok=True)
    # Never let coach data end up in a commit, whatever the repo's .gitignore says.
    ignore = DATA_DIR / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n")
    return d
