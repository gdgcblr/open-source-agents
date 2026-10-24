"""Application settings, loaded from environment variables and the project `.env` file."""

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The value shipped in .env.example. It is public, so it must never protect real call data.
EXAMPLE_DASHBOARD_PASSWORD = "change-me-to-a-long-random-password"


class Settings(BaseSettings):
    """Typed configuration. Field names map to upper-case environment variables."""

    model_config = SettingsConfigDict(
        # The backend reads the shared `.env` at the project root during local development;
        # in Docker the same values arrive as real environment variables via `env_file`.
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application ---
    log_level: str = "INFO"
    database_url: str = "sqlite+aiosqlite:///./data/reception_calls.db"
    recordings_dir: Path = Path("./data/recordings")
    max_upload_mb: int = 100
    public_base_url: str = "http://localhost:8000"

    # --- Dashboard (HTTP Basic auth) ---
    dashboard_username: str = "admin"
    dashboard_password: SecretStr

    # --- Deepgram ---
    deepgram_api_key: SecretStr
    # Flux Multilingual understands English, Hindi and callers who mix the two.
    deepgram_listen_model: str = "flux-general-multi"
    deepgram_language_hints: str = "en,hi"
    # One voice per language; the receptionist switches when the caller prefers Hindi.
    deepgram_speak_model: str = "flux-priya-en"
    deepgram_speak_model_hindi: str = "flux-anjali-hi"
    deepgram_diarize_model: str = "nova-3"
    # "multi" transcribes recordings that mix languages; use "en" for English-only lines.
    deepgram_diarize_language: str = "multi"

    # --- Hospital the reception agent answers for ---
    # Directory with hospital.md (information) and doctors.csv (roster for booking). It seeds
    # the database on first start; afterwards the hospital is edited from the dashboard.
    hospital_dir: Path = Path("knowledge/sahyadri-deccan")
    hospital_timezone: str = "Asia/Kolkata"
    # Appointments can only be booked this far ahead. A caller who needs a later time is told
    # so and the call ends.
    booking_window_hours: int = Field(default=72, ge=1, le=24 * 60)

    # --- Voice agent behaviour ---
    agent_llm_provider: str = "anthropic"
    agent_llm_model: str = "claude-sonnet-5"
    agent_prompt: str | None = None
    agent_greeting: str | None = None

    # --- Guardrails ---
    # The receptionist says goodbye and hangs up at this length, so a line left open (or a
    # caller keeping the agent talking) can't run up Deepgram charges.
    max_call_minutes: float = Field(default=15, gt=0, le=120)
    # Stops one call from taking a doctor's whole day of slots.
    max_bookings_per_call: int = Field(default=3, ge=1, le=20)
    # Answers to "English or Hindi?" that are neither, before the call ends.
    max_language_attempts: int = Field(default=3, ge=1, le=10)

    # --- Cost estimates (USD, Deepgram pay-as-you-go list prices) ---
    # Voice Agent API per connected minute: 0.163 for Advanced-tier LLMs such as
    # claude-sonnet-5, 0.075 for Standard-tier ones such as claude-haiku-4-5.
    voice_agent_usd_per_minute: float = 0.163
    # Pre-recorded Nova-3 transcription per audio minute (diarization included): 0.0052 for
    # multilingual, 0.0043 if DEEPGRAM_DIARIZE_LANGUAGE is a single language such as "en".
    transcription_usd_per_minute: float = 0.0052

    # --- Twilio ---
    twilio_account_sid: str = ""
    twilio_auth_token: SecretStr = SecretStr("")
    twilio_validate_signature: bool = True
    record_calls: bool = True

    @field_validator("dashboard_password")
    @classmethod
    def _reject_example_password(cls, value: SecretStr) -> SecretStr:
        if value.get_secret_value() in ("", EXAMPLE_DASHBOARD_PASSWORD):
            raise ValueError("set DASHBOARD_PASSWORD in .env to your own value")
        return value

    @field_validator("hospital_timezone")
    @classmethod
    def _require_known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(
                f"unknown timezone {value!r}; use an IANA name like Asia/Kolkata"
            ) from exc
        return value

    @property
    def language_hints(self) -> list[str]:
        return [code.strip() for code in self.deepgram_language_hints.split(",") if code.strip()]

    @property
    def twilio_configured(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_auth_token.get_secret_value())

    def public_url(self, path: str) -> str:
        """Absolute public URL for `path`, as Twilio sees it (used for webhooks and signatures)."""
        return f"{self.public_base_url.rstrip('/')}{path}"

    def public_ws_url(self, path: str) -> str:
        """Absolute public WebSocket URL for `path` (`https` becomes `wss`)."""
        url = self.public_url(path)
        if url.startswith("https://"):
            return "wss://" + url.removeprefix("https://")
        return "ws://" + url.removeprefix("http://")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # required fields come from the environment
