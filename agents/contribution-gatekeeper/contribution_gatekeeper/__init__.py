"""contribution-gatekeeper: review open-source contributions against the repo's own CONTRIBUTING.md."""

from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from . import agent  # noqa: E402,F401  (exposes root_agent for `adk web`)
