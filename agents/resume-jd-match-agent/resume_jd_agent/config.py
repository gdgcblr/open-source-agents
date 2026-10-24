"""Central configuration for the Resume <-> JD Match Agent.

All model parameters, cache rules, file limits, security guards, and shared
state keys live here so settings are not scattered across multiple files.
"""

import os

from google.genai import types

# --- Model & Generation Settings ---------------------------------------------
MODEL_NAME = os.getenv("RESUME_JD_MODEL", "gemini-3.8-flash")
OCR_MODEL = os.getenv("RESUME_JD_OCR_MODEL", "gemini-3.8-flash")
OCR_ENABLED_ENV = "RESUME_JD_OCR"

TEMPERATURE = float(os.getenv("RESUME_JD_TEMPERATURE", "0.2"))
MAX_OUTPUT_TOKENS = int(os.getenv("RESUME_JD_MAX_OUTPUT_TOKENS", "4096"))
THINKING_BUDGET = int(os.getenv("RESUME_JD_THINKING_BUDGET", "1024"))

RETRY_ATTEMPTS = int(os.getenv("RESUME_JD_RETRY_ATTEMPTS", "3"))
RETRY_INITIAL_DELAY = float(os.getenv("RESUME_JD_RETRY_INITIAL_DELAY", "10"))
RETRY_MAX_DELAY = float(os.getenv("RESUME_JD_RETRY_MAX_DELAY", "60"))
RETRY_OPTIONS = types.HttpRetryOptions(
    attempts=RETRY_ATTEMPTS,
    initial_delay=RETRY_INITIAL_DELAY,
    max_delay=RETRY_MAX_DELAY,
)

# --- Cache Settings -----------------------------------------------------------
CACHE_VERSION = "3"
CACHE_DIR = os.getenv(
    "RESUME_JD_CACHE_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "reports"),
)
CACHE_ENV = "RESUME_JD_CACHE"
MAX_AGE_SECONDS = int(os.getenv("RESUME_JD_CACHE_MAX_AGE", str(30 * 24 * 3600)))

# --- Document & Size Limits ---------------------------------------------------
MAX_FILE_BYTES = 5_000_000
MAX_PDF_PAGES = 10
MAX_DOC_CHARS = 20_000

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".txt", ".md")
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# --- Security & File Access Limits --------------------------------------------
ALLOW_FILE_PATHS_ENV = "RESUME_JD_ALLOW_FILE_PATHS"
ALLOWED_DIRS_ENV = "RESUME_JD_ALLOWED_DIRS"


def allow_file_paths() -> bool:
    """True when reading files by path is permitted."""
    return os.getenv(ALLOW_FILE_PATHS_ENV, "on").lower() not in ("off", "0", "false", "no")


def get_allowed_folders() -> list[str]:
    """Returns the list of allowed root directories for file path reads, if any.

    Configured via the RESUME_JD_ALLOWED_DIRS environment variable as a
    comma- or colon-separated list of directories. If empty, any path is
    permitted (subject to allow_file_paths()).
    """
    raw = os.getenv(ALLOWED_DIRS_ENV, "").strip()
    if not raw:
        return []
    separator = ":" if ":" in raw and not raw.startswith(":") and "\\" not in raw else ","
    dirs = [d.strip() for d in raw.split(separator) if d.strip()]
    return [os.path.realpath(os.path.abspath(os.path.expanduser(d))) for d in dirs]


# --- Guardrail Limits & Headings ----------------------------------------------
MAX_MODEL_CALLS_PER_TURN = 4
MIN_DOCS_CHARS = 300

REQUIRED_HEADINGS = [
    "## 1. Match Score",
    "## 2. Matched Skills",
    "## 3. Missing Skills & Keywords",
    "## 4. Bullet Rewrites",
    "## 5. Top 3 Fixes Before Applying",
]
COVER_LETTER_HEADING = "## Cover Letter"

ASK_FOR_INPUTS = (
    "To build your match report I need two things:\n\n"
    "1. **Your resume**: upload a PDF, .docx or .txt with the attach (+) button, give a "
    "file path (e.g. `samples/sample_resume.txt`), or paste the text.\n"
    "2. **The job description**: paste it, upload it, or give a file path. Several JDs? "
    "Send them all and I will rank them.\n\n"
    "Send both in one message to get the full report."
)

# --- State Keys & Prefixes ---------------------------------------------------
EXPORT_STATE = "temp:export"
DOWNLOAD_PREFIX = "> Download:"
UPLOAD_PREFIX = "upload:"
UPLOADS_STATE_KEY = "uploads"
RESUME_STATE_KEY = "resume_text"
MISSING_STATE_KEY = "missing_skills"
JD_STATE_KEY = "jd_text"
CACHE_KEY_STATE = "temp:report_cache_key"
