import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = PROJECT_ROOT / "tests" / "fixtures"
FAKE_SERVER = PROJECT_ROOT / "tests" / "fake_mcp_server.py"

# Make the package importable without installing it.
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def benign_tools():
    return json.loads((FIXTURES / "benign_tools.json").read_text(encoding="utf-8"))


@pytest.fixture
def poisoned_tools():
    return json.loads((FIXTURES / "poisoned_tools.json").read_text(encoding="utf-8"))["tools"]


@pytest.fixture
def fake_server_cmd():
    return [sys.executable, str(FAKE_SERVER)]


@pytest.fixture
def http_server():
    """Factory: http_server(mode=..., response_format=..., token=...) -> base URL."""
    from fake_mcp_http_server import start

    servers = []

    def factory(**kwargs):
        server, url = start(**kwargs)
        servers.append(server)
        return url

    yield factory
    for server in servers:
        server.shutdown()
