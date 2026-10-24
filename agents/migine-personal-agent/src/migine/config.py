import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


def local_url(value: str) -> str:
    url = urlparse(value)
    if (
        url.scheme != "http"
        or url.hostname not in {"localhost", "127.0.0.1", "host.docker.internal"}
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
    ):
        raise ValueError("Only local HTTP services are permitted.")
    return value.rstrip("/")


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    timezone: str
    ollama_url: str
    chat_model: str
    embedding_model: str
    connector_url: str | None
    token_file: Path | None

    @classmethod
    def load(cls):
        load_dotenv(override=False)
        timezone = os.getenv("MIGINE_TIMEZONE", "Asia/Kolkata")
        ZoneInfo(timezone)
        model = os.getenv("MIGINE_CHAT_MODEL", "gemma4:e4b")
        embedding = os.getenv("MIGINE_EMBEDDING_MODEL", "embeddinggemma")
        if any(
            "/" in m or "cloud" in m or not m.startswith(prefix)
            for m, prefix in [(model, "gemma"), (embedding, "embeddinggemma")]
        ):
            raise ValueError("Use local Gemma and EmbeddingGemma model tags.")
        connector = os.getenv("MIGINE_MAC_CONNECTOR_URL")
        token = os.getenv("MIGINE_MAC_CONNECTOR_TOKEN_FILE")
        return cls(
            Path(os.getenv("MIGINE_DATA_DIR", "~/.local/share/migine")).expanduser(),
            timezone,
            local_url(os.getenv("OLLAMA_API_BASE", "http://127.0.0.1:11434")),
            model,
            embedding,
            local_url(connector) if connector else None,
            Path(token).expanduser() if token else None,
        )
