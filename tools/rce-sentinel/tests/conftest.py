from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from rce_sentinel.config import Settings, load_settings
from rce_sentinel.engine import Scanner
from rce_sentinel.memory.store import Store
from rce_sentinel.orchestrator.llm import MockProvider, ModelRegistry

FIXTURES = Path(__file__).parent / "fixtures"
TOOL_ROOT = Path(__file__).parents[1]


@pytest.fixture(autouse=True)
def offline_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RCE_SENTINEL_OFFLINE", "1")
    monkeypatch.setenv("RCE_SENTINEL_PROVIDER", "mock")
    monkeypatch.setenv("RCE_SENTINEL_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("RCE_SENTINEL_KEY_FILE", str(tmp_path / "test.key"))
    for var in ("CAVEMAN", "RCE_SENTINEL_CAVEMAN_PROBE", "RCE_SENTINEL_SHADOW_RATE",
                "RCE_SENTINEL_CONFIG_DIR", "SLACK_WEBHOOK_URL", "DISCORD_WEBHOOK_URL"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(FIXTURES / "vuln_repo", dest)
    return dest


@pytest.fixture
def settings(repo: Path) -> Settings:
    return load_settings(repo)


def seed_osv(scanner: Scanner) -> None:
    records = json.loads((FIXTURES / "osv_seed.json").read_text())
    scanner.osv.import_seed(records)


@pytest.fixture
def scanner(settings: Settings) -> Scanner:
    store = Store(settings.db_path)
    registry = ModelRegistry(settings.models, "mock")
    sc = Scanner(settings, store=store, provider=MockProvider(), registry=registry)
    seed_osv(sc)
    return sc


def git(repo: Path, *args: str) -> str:
    res = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                         check=True)
    return res.stdout


@pytest.fixture
def git_repo(repo: Path) -> Path:
    git(repo, "init", "-q", "-b", "task/rce-sentinel-test")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "test")
    git(repo, "config", "core.hooksPath", "/dev/null")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "fixture")
    return repo
