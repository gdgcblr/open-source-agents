"""Configuration and environment management for GoalFlow."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Automatically load .env from project root or current working directory
load_dotenv()

DEFAULT_DB_PATH = os.getenv("GOALFLOW_DB_PATH", "goalflow.db")
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


def get_gemini_api_key() -> str | None:
    """Return the configured GEMINI_API_KEY or None."""
    return os.getenv("GEMINI_API_KEY")


def get_db_path() -> str:
    """Return the database file path."""
    return os.getenv("GOALFLOW_DB_PATH", DEFAULT_DB_PATH)


def get_model_name() -> str:
    """Return the configured Gemini model name."""
    return os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
