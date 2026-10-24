import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = PROJECT_ROOT / "examples" / "shop_returns"
EXAMPLE_CONFIG = EXAMPLE / "murphy.yaml"
SCRIPTED_CONFIG = Path(__file__).resolve().parent / "fixtures" / "scripted.yaml"
SHOP_UPSTREAM = {
    "name": "shop",
    "command": [sys.executable, "-m", "backend.shop_server"],
    "env": {"STRESS_TODAY": "2026-10-24"},
    "cwd": str(EXAMPLE),
}

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _env(run_dir: Path) -> dict:
    return {**os.environ, "MURPHY_RUN_DIR": str(run_dir)}  # same as the orchestrator: inherit the caller's env


@asynccontextmanager
async def backend_client(run_dir: Path):
    transport = StdioTransport(sys.executable, ["-m", "backend.shop_server"],
                               env={**_env(run_dir), "STRESS_TODAY": "2026-10-24"}, cwd=str(EXAMPLE))
    async with Client(transport) as client:
        yield client


@asynccontextmanager
async def proxy_client(run_dir: Path, faults: list | None = None, policy: dict | None = None,
                       upstreams: list | None = None, seed: int = 7):
    spec = {"upstreams": upstreams or [SHOP_UPSTREAM], "faults": faults or [],
            "policy": policy or {"mode": "monitor", "rules": []}, "seed": seed}
    (run_dir / "proxy.json").write_text(json.dumps(spec))
    transport = StdioTransport(sys.executable, ["-m", "murphy.proxy", str(run_dir)],
                               env=_env(run_dir), cwd=str(PROJECT_ROOT))
    async with Client(transport) as client:
        yield client


@pytest.fixture
def run_dir(tmp_path):
    return tmp_path


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def read_state(run_dir: Path) -> dict:
    return json.loads((run_dir / "state.json").read_text())
