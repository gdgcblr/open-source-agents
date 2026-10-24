"""adk-memshield: Zero-trust multi-tenant semantic memory service for Google ADK."""

from .config import MemShieldConfig
from .embedder import EmbedFn, MemShieldEmbedder
from .service import MemShieldMemoryService, QueryTelemetry, register_adk_uri

__version__ = "0.1.0"

__all__ = [
    "EmbedFn",
    "MemShieldConfig",
    "MemShieldEmbedder",
    "MemShieldMemoryService",
    "QueryTelemetry",
    "register_adk_uri",
]
