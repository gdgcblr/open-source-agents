"""Entry point for `adk web adk_agents` and `adk run adk_agents/issue_scout_agent`.

ADK loads agents from a folder of packages, so this thin wrapper puts the project root on
the import path, loads the project's .env, and re-exports the real agent.
"""

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from issue_scout.cli import load_dotenv  # noqa: E402

load_dotenv(PROJECT_DIR / ".env")

from issue_scout.agent import root_agent  # noqa: E402,F401
