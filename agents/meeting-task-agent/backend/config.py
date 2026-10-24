import os
from pathlib import Path
from pydantic import BaseModel
from dotenv import load_dotenv

# Load .env file
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

class Settings(BaseModel):
    # Gemma & LLM Inference Configuration
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    gemma_model: str = os.getenv("GEMMA_MODEL", "gemma2:9b")
    vllm_base_url: str = os.getenv("VLLM_BASE_URL", "")
    vllm_api_key: str = os.getenv("VLLM_API_KEY", "")
    
    # Google OAuth & Workspace Settings
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    
    # Server & Persistence
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    db_path: str = os.getenv("DB_PATH", str(BASE_DIR / "meetingmind.db"))
    nudge_grace_hours: int = int(os.getenv("NUDGE_GRACE_HOURS", "2"))

settings = Settings()

