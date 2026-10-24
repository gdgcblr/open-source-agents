"""Entry point for the ADK Web UI.

Run from the project folder:
    adk web adk_web
then open http://127.0.0.1:8000 and pick "good_first_issue".
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:  # load the project's .env (existing environment variables win)
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=False)
except ImportError:
    pass

try:  # verify HTTPS with the OS certificate store (works behind TLS-inspecting proxies)
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

from good_first_issue_agent.web_agent import build_root_agent  # noqa: E402

root_agent = build_root_agent()
