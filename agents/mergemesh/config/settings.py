"""Environment-driven settings and local runtime readiness checks for MergeMesh.

Designed for local-first operation with zero external API credit requirements.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_ROOT = PROJECT_ROOT / "fixtures" / "scenarios"
REPORTS_ROOT = PROJECT_ROOT / "reports"

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv()

AIMode = Literal["local", "deterministic", "gemini", "hybrid"]
GeminiBackend = Literal["developer_api", "vertex_ai"]

VALID_AI_MODES: set[str] = {"local", "deterministic", "gemini", "hybrid"}
VALID_GEMINI_BACKENDS: set[str] = {"developer_api", "vertex_ai"}

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "gemma4:e4b"
LIGHTWEIGHT_OLLAMA_MODEL = "gemma4:e2b"
DEFAULT_HOSTED_GEMMA_MODEL = "gemma-4-26b-a4b-it"
SUPPORTED_LOCAL_MODELS: tuple[str, ...] = (
    "gemma4:e4b",
    "gemma4:e2b",
    "gemma3:4b",
    "gemma2:2b",
)
SUPPORTED_HOSTED_GEMMA_MODELS: tuple[str, ...] = (
    "gemma-4-26b-a4b-it",
    "gemma-4-31b-it",
)


def _is_loopback_url(url: str) -> bool:
    """Ensure Ollama checks only ever contact loopback/localhost addresses."""
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        return host in {"localhost", "127.0.0.1", "::1"}
    except Exception:
        return False


def detect_ollama_cli_path() -> str | None:
    """Check whether the Ollama executable exists in PATH or common local install locations."""
    in_path = shutil.which("ollama")
    if in_path:
        return in_path

    candidate_paths: list[Path] = []
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        candidate_paths.append(Path(local_app_data) / "Programs" / "Ollama" / "ollama.exe")
    prog_files = os.environ.get("ProgramFiles", "")
    if prog_files:
        candidate_paths.append(Path(prog_files) / "Ollama" / "ollama.exe")
    candidate_paths.extend(
        [
            Path("/usr/local/bin/ollama"),
            Path("/opt/homebrew/bin/ollama"),
            Path("/usr/bin/ollama"),
        ]
    )
    for candidate in candidate_paths:
        try:
            if candidate.is_file():
                return str(candidate)
        except OSError:
            continue
    return None


@dataclass(frozen=True)
class ProviderReadiness:
    ollama_reachable: bool
    ollama_model_installed: bool
    ollama_available_models: list[str]
    ollama_status_message: str
    gemini_configured: bool
    gemini_backend: str
    gemini_status_message: str
    ollama_cli_path: str | None = None
    ollama_recovery_hint: str = ""


@dataclass(frozen=True)
class AppSettings:
    ai_mode: AIMode
    ollama_base_url: str
    ollama_model: str
    gemini_model: str
    gemini_backend: GeminiBackend
    use_vertex_ai: bool
    google_cloud_project: str
    google_cloud_location: str
    has_gemini_api_key: bool
    allow_local_fallback: bool
    ai_request_timeout_seconds: int
    ai_max_output_tokens: int
    ai_max_calls_per_analysis: int
    test_runner_timeout_seconds: int
    fixtures_root: Path = FIXTURES_ROOT
    reports_root: Path = REPORTS_ROOT

    def get_active_gemini_key(self) -> str | None:
        """Return API key for optional config inspection only; never log or display."""
        google_key = os.environ.get("GOOGLE_API_KEY", "").strip()
        if google_key:
            return google_key
        gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if gemini_key:
            return gemini_key
        return None

    def is_gemini_configured(self) -> bool:
        if self.use_vertex_ai or self.gemini_backend == "vertex_ai":
            return bool(self.google_cloud_project and self.google_cloud_location)
        return self.has_gemini_api_key


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str | None, default: int, minimum: int = 1) -> int:
    if value is None or value.strip() == "":
        return default
    try:
        parsed = int(value.strip())
        return max(parsed, minimum)
    except ValueError:
        return default


def load_settings(override_ai_mode: str | None = None) -> AppSettings:
    """Load and validate application settings from environment variables."""
    raw_mode = (override_ai_mode or os.environ.get("MERGEMESH_AI_MODE", "local")).strip().lower()
    if raw_mode not in VALID_AI_MODES:
        raise ValueError(
            f"Invalid MERGEMESH_AI_MODE '{raw_mode}'. Expected one of: {sorted(VALID_AI_MODES)}"
        )

    raw_backend = os.environ.get("GEMINI_BACKEND", "developer_api").strip().lower()
    if raw_backend not in VALID_GEMINI_BACKENDS:
        raw_backend = "developer_api"

    use_vertex = _parse_bool(os.environ.get("GOOGLE_GENAI_USE_VERTEXAI"), default=(raw_backend == "vertex_ai"))
    if use_vertex:
        raw_backend = "vertex_ai"

    google_key = os.environ.get("GOOGLE_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    has_key = bool(google_key or gemini_key)

    gemini_model = os.environ.get("GEMINI_MODEL", DEFAULT_HOSTED_GEMMA_MODEL).strip()
    if not gemini_model or gemini_model == "SET_A_SUPPORTED_MODEL_ID":
        gemini_model = DEFAULT_HOSTED_GEMMA_MODEL

    ollama_url = os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).strip().rstrip("/")
    if not ollama_url:
        ollama_url = DEFAULT_OLLAMA_BASE_URL
    ollama_model = os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL).strip()
    if not ollama_model:
        ollama_model = DEFAULT_OLLAMA_MODEL

    return AppSettings(
        ai_mode=raw_mode,  # type: ignore[arg-type]
        ollama_base_url=ollama_url,
        ollama_model=ollama_model,
        gemini_model=gemini_model,
        gemini_backend=raw_backend,  # type: ignore[arg-type]
        use_vertex_ai=use_vertex,
        google_cloud_project=os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip(),
        google_cloud_location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1").strip(),
        has_gemini_api_key=has_key,
        allow_local_fallback=_parse_bool(os.environ.get("ALLOW_LOCAL_FALLBACK"), default=True),
        ai_request_timeout_seconds=_parse_int(os.environ.get("AI_REQUEST_TIMEOUT_SECONDS"), default=25),
        ai_max_output_tokens=_parse_int(os.environ.get("AI_MAX_OUTPUT_TOKENS"), default=1200),
        ai_max_calls_per_analysis=_parse_int(os.environ.get("AI_MAX_CALLS_PER_ANALYSIS"), default=2),
        test_runner_timeout_seconds=_parse_int(os.environ.get("TEST_RUNNER_TIMEOUT_SECONDS"), default=15),
    )


def check_provider_readiness(settings: AppSettings, timeout_sec: float = 1.5) -> ProviderReadiness:
    """Check whether local Ollama is reachable without making any external network requests."""
    ollama_reachable = False
    ollama_model_installed = False
    available_models: list[str] = []
    cli_path = detect_ollama_cli_path()
    recovery_hint = ""
    ollama_msg = f"Ollama not reachable at {settings.ollama_base_url}"

    if not _is_loopback_url(settings.ollama_base_url):
        ollama_msg = (
            f"Blocked non-local OLLAMA_BASE_URL ({settings.ollama_base_url}); "
            "MergeMesh enforces local-only inference."
        )
        recovery_hint = f"Set OLLAMA_BASE_URL={DEFAULT_OLLAMA_BASE_URL} in .env."
    else:
        try:
            resp = requests.get(f"{settings.ollama_base_url}/api/tags", timeout=timeout_sec)
            if resp.status_code == 200:
                ollama_reachable = True
                data = resp.json()
                models_list = data.get("models", [])
                available_models = [str(m.get("name", "")) for m in models_list if m.get("name")]
                target = settings.ollama_model
                ollama_model_installed = any(
                    m == target or m.startswith(f"{target}:") or target in m
                    for m in available_models
                )
                if ollama_model_installed:
                    ollama_msg = f"Ollama ready ({settings.ollama_model})"
                else:
                    ollama_msg = (
                        f"Ollama running, but model '{settings.ollama_model}' is not pulled "
                        f"(found: {', '.join(available_models) if available_models else 'none'})"
                    )
                    recovery_hint = f"Run: ollama pull {settings.ollama_model}"
            else:
                ollama_msg = f"Ollama returned HTTP {resp.status_code}"
                recovery_hint = "Verify the local Ollama daemon status on port 11434."
        except Exception:
            if cli_path:
                ollama_msg = (
                    f"Ollama installed ({cli_path}) but service is offline ({settings.ollama_base_url}) — "
                    "deterministic fallback active"
                )
                recovery_hint = f'Start Ollama with `"{cli_path}" serve` and ensure `{settings.ollama_model}` is pulled.'
            else:
                ollama_msg = (
                    f"Ollama service offline and CLI not found ({settings.ollama_base_url}) — "
                    "deterministic fallback active"
                )
                recovery_hint = (
                    f"Install Ollama from https://ollama.com, run `ollama serve`, and pull `{settings.ollama_model}` "
                    f"(or `{LIGHTWEIGHT_OLLAMA_MODEL}` for lower memory)."
                )

    gemini_ready = settings.is_gemini_configured()
    if settings.gemini_backend == "vertex_ai":
        if gemini_ready:
            gemini_msg = f"Vertex AI configured ({settings.gemini_model})"
        else:
            gemini_msg = "Vertex AI not configured (GOOGLE_CLOUD_PROJECT missing)"
    else:
        if gemini_ready:
            gemini_msg = f"Hosted Gemma / Gemini API configured ({settings.gemini_model})"
        else:
            gemini_msg = "Gemini API key not configured (set GEMINI_API_KEY in .env for hosted mode)"

    return ProviderReadiness(
        ollama_reachable=ollama_reachable,
        ollama_model_installed=ollama_model_installed,
        ollama_available_models=available_models,
        ollama_status_message=ollama_msg,
        gemini_configured=gemini_ready,
        gemini_backend=settings.gemini_backend,
        gemini_status_message=gemini_msg,
        ollama_cli_path=cli_path,
        ollama_recovery_hint=recovery_hint,
    )
