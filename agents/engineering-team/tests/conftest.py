from __future__ import annotations

from types import SimpleNamespace

import pytest

from shared_memory import handoff as team_module
from shared_memory.engine import SQLiteStore
from shared_memory.guardrails import GuardrailLog
from mock_llm import MockLlm


class SpyLlm(MockLlm):
    """The mock model, recording every request it receives in ``SpyLlm.requests``."""

    async def generate_content_async(self, llm_request, stream=False):
        SpyLlm.requests.append(llm_request)
        async for response in super().generate_content_async(llm_request, stream):
            yield response


SpyLlm.requests = []


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("TEAM_WORKSPACE", str(tmp_path / "workspace"))
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    SpyLlm.requests = []
    monkeypatch.setattr(team_module, "MockLlm", SpyLlm)


@pytest.fixture()
def store(tmp_path):
    with SQLiteStore(tmp_path / "team.db") as s:
        yield s


@pytest.fixture()
def log():
    return GuardrailLog()


@pytest.fixture()
def team(store, log):
    return team_module.build_team(store, mock=True, log=log)


def tool_context(task_id: str = "task-test", role: str = "junior"):
    """Function tools only read ``tool_context.state``."""
    return SimpleNamespace(state={"task_id": task_id, "role": role})
