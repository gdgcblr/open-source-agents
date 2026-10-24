"""
Configuration management for NammaRaktha.
Loads from environment variables or .env file.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Search for .env in current directory or parent directories
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")
PORT = int(os.getenv("PORT", "8080"))
HOST = os.getenv("HOST", "localhost")
LOG_LEVEL = os.getenv("LOG_LEVEL", "info")
