import importlib.util
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from dotenv import dotenv_values

from migine.config import Settings


@pytest.mark.parametrize("embedding_installed", [True, False])
@pytest.mark.parametrize("custom_helper", [None, "/custom/MigineConnector"])
def test_setup_preserves_settings_and_pulls_only_missing_models(
    tmp_path, monkeypatch, embedding_installed, custom_helper
):
    path = Path(__file__).parents[1] / "scripts/setup_local.py"
    spec = importlib.util.spec_from_file_location("setup_local", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / ".env").write_text("MIGINE_TIMEZONE=Asia/Kolkata\n")
    if custom_helper:
        with (tmp_path / ".env").open("a") as stream:
            stream.write(f"MIGINE_MAC_HELPER={custom_helper}\n")
    settings = Settings(
        tmp_path / "data",
        "Asia/Kolkata",
        "http://127.0.0.1:11434",
        "gemma4:e4b",
        "embeddinggemma",
        None,
        None,
    )
    monkeypatch.setattr(module, "Settings", SimpleNamespace(load=lambda: settings))
    monkeypatch.setattr(module, "load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.delenv("MIGINE_MAC_HELPER", raising=False)
    if custom_helper:
        monkeypatch.setenv("MIGINE_MAC_HELPER", custom_helper)
    calls = []
    monkeypatch.setattr(module.subprocess, "run", lambda args, **kwargs: calls.append(args))

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def get(self, url):
            names = [settings.chat_model]
            if embedding_installed:
                names.append("embeddinggemma:latest")
            return httpx.Response(
                200,
                request=httpx.Request("GET", url),
                json={"models": [{"name": name} for name in names]},
            )

    monkeypatch.setattr(module.httpx, "Client", Client)
    module.configure(tmp_path)
    saved = dotenv_values(tmp_path / ".env")
    assert saved["MIGINE_TIMEZONE"] == "Asia/Kolkata"
    assert saved["MIGINE_MAC_HELPER"] == (
        custom_helper or str(tmp_path / "build/MigineConnector.app/Contents/MacOS/MigineConnector")
    )
    pulls = [command for command in calls if command[:2] == ["ollama", "pull"]]
    assert pulls == ([] if embedding_installed else [["ollama", "pull", "embeddinggemma"]])
    assert calls[0] == ["sh", str(tmp_path / "scripts/build-mac-helper.sh")]
    assert not any("sync" in call or "extract" in call for call in calls)


def test_run_script_starts_local_web_from_project_directory(tmp_path):
    project = tmp_path / "project with spaces"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    (project / ".env").write_text("MIGINE_DATA_DIR=./data\n")
    run = scripts / "run-local.sh"
    run.write_text((Path(__file__).parents[1] / "scripts/run-local.sh").read_text())
    commands = tmp_path / "commands"
    commands.mkdir()
    uv = commands / "uv"
    uv.write_text('#!/bin/sh\npwd\nprintf "%s\\n" "$@"\n')
    uv.chmod(0o755)
    response = subprocess.run(
        ["sh", str(run)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
        env=os.environ | {"PATH": str(commands) + ":" + os.environ["PATH"]},
    )
    assert str(project) in response.stdout
    assert "run\n--frozen\nadk\nweb\nexamples/web\n--host\n127.0.0.1" in response.stdout
    assert "--max_llm_calls\n8" in response.stdout
    assert "demo" not in response.stdout
