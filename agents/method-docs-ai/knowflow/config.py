import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    chat_model: str = os.getenv("GEMINI_CHAT_MODEL", "gemini-2.5-flash")
    knowledge_dir: Path = Path(os.getenv("KNOWLEDGE_DIR", "knowledge_base"))
    index_dir: Path = Path(os.getenv("INDEX_DIR", ".knowflow_index"))
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "1200"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "180"))
    top_k: int = int(os.getenv("TOP_K", "5"))
    min_relevance: float = float(os.getenv("MIN_RELEVANCE", "0.08"))

settings = Settings()
