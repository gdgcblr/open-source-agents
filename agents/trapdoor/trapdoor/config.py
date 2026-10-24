"""Central config — all settings come from here, nowhere else."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
    MODEL_NAME: str = os.environ.get("MODEL_NAME", "gemini-3.7-flash")
    MAX_AGENT_TURNS: int = int(os.environ.get("MAX_AGENT_TURNS", "10"))
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

    @classmethod
    def validate(cls) -> None:
        if not cls.GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY is not set.\n"
                "Copy .env.example to .env and add your key from https://aistudio.google.com"
            )


cfg = Config()
