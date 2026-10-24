"""Configuration loading. Secrets come from the environment (.env), never from config.yaml."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


@dataclass
class RepoConfig:
    name: str  # "owner/repo"
    base_branch: str | None = None  # defaults to the PR's base branch
    checks: list[str] = field(default_factory=list)  # validation commands; auto-detected if empty
    clone_url: str | None = None  # defaults to SSH: git@github.com:owner/repo.git


@dataclass
class Config:
    repos: list[RepoConfig]
    poll_interval_seconds: int = 120
    model: str = "ollama_chat/qwen2.5-coder:3b"
    api_base: str = "http://localhost:11434"
    num_ctx: int = 8192
    strict_local: bool = True
    workspace_dir: Path = ROOT / "workspaces"
    db_path: Path = ROOT / "data" / "pr_agent.db"
    max_repair_attempts: int = 2
    max_llm_calls: int = 25
    command_timeout_seconds: int = 600
    max_diff_chars: int = 12000
    skip_drafts: bool = True
    exclude_labels: list[str] = field(default_factory=list)
    exclude_authors: list[str] = field(default_factory=list)
    python_executable: str | None = None  # interpreter for "python -m ..." checks
    allowed_commands: list[str] = field(default_factory=list)  # extra executables beyond the defaults
    worthwhile_criteria: list[str] = field(default_factory=list)
    host: str = "127.0.0.1"
    port: int = 8765
    github_token: str = ""

    def assert_local_only(self) -> None:
        """Strict local-only mode: refuse any model that is not served from this machine."""
        if not self.strict_local:
            return
        if not self.model.startswith(("ollama/", "ollama_chat/")):
            raise ValueError(f"strict_local is on, but model '{self.model}' is not an Ollama model.")
        host = urlparse(self.api_base).hostname or ""
        if host not in LOCAL_HOSTS:
            raise ValueError(f"strict_local is on, but api_base '{self.api_base}' is not a local address.")


def load_config(path: str | Path | None = None) -> Config:
    load_dotenv(ROOT / ".env")
    path = Path(path or os.environ.get("PR_AGENT_CONFIG") or ROOT / "config.yaml")
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}. Copy config.example.yaml to config.yaml.")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    repos = [RepoConfig(**r) if isinstance(r, dict) else RepoConfig(name=r) for r in raw.pop("repos", [])]
    for key in ("workspace_dir", "db_path"):
        if key in raw:
            p = Path(raw[key])
            raw[key] = p if p.is_absolute() else ROOT / p
    cfg = Config(repos=repos, **raw)
    cfg.github_token = os.environ.get("GITHUB_TOKEN", "")
    cfg.assert_local_only()
    return cfg
