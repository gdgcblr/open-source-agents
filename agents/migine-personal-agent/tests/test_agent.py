import asyncio
import json
from pathlib import Path

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from migine.adapters import NativeToolError
from migine.agent import build_agent, chat
from migine.config import Settings
from migine.demo import load_demo
from migine.storage import Store


def settings_at(path):
    return Settings(
        path, "Asia/Kolkata", "http://127.0.0.1:11434", "gemma4:e4b", "embeddinggemma", None, None
    )


class ScriptedModel(BaseLlm):
    model: str = "scripted"
    calls: int = 0

    async def generate_content_async(self, llm_request, stream=False):
        self.calls += 1
        if self.calls == 1:
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name="summary_month", args={"month": "2026-10"}
                            )
                        )
                    ],
                )
            )
        else:
            # Verify the real ADK tool result reaches the model.
            responses = [
                p.function_response
                for c in llm_request.contents
                for p in c.parts or []
                if p.function_response
            ]
            assert responses
            assert "279.00" in json.dumps(responses[-1].response)
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(text="Internal test reasoning", thought=True),
                        types.Part(text="Synthetic subscription total: INR 279.00."),
                    ],
                )
            )


def test_adk_tool_and_persistent_session(tmp_path, monkeypatch):
    settings = settings_at(tmp_path)
    store = Store(tmp_path)
    load_demo(store, "2026-10")
    agent = build_agent(settings, store, None)
    assert {t.__name__ for t in agent.tools} == {
        "search_mail",
        "summary_month",
        "upcoming_events",
        "find_contacts",
        "read_preferences",
        "propose_change",
    }
    agent.model = ScriptedModel()
    monkeypatch.setattr("migine.agent.build_agent", lambda *_args: agent)
    result = asyncio.run(chat(settings, store, None, "Summarise October.", "test"))
    assert "279.00" in result
    assert "Internal test reasoning" not in result
    assert (Path(tmp_path) / "sessions.sqlite3").is_file()


def test_tool_proposal_has_no_execution_path(tmp_path):
    store = Store(tmp_path)
    agent = build_agent(settings_at(tmp_path), store, None)
    proposal_tool = next(t for t in agent.tools if t.__name__ == "propose_change")
    result = proposal_tool("mail.flag", '{"id":"synthetic", "value":true}')
    assert result["preview"]["id"] == "synthetic"
    with store.connect() as db:
        assert db.execute("SELECT state FROM action_requests").fetchone()[0] == "pending"


def test_calendar_permission_failure_is_a_tool_result(tmp_path, monkeypatch):
    class DeniedAdapter:
        def call(self, *_args):
            raise NativeToolError("calendar.read", "permission_required")

    class PermissionModel(BaseLlm):
        model: str = "scripted"
        calls: int = 0

        async def generate_content_async(self, llm_request, stream=False):
            self.calls += 1
            if self.calls == 1:
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part(
                                function_call=types.FunctionCall(
                                    name="upcoming_events", args={"days": 1}
                                )
                            )
                        ],
                    )
                )
            else:
                responses = [
                    p.function_response
                    for c in llm_request.contents
                    for p in c.parts or []
                    if p.function_response
                ]
                result = responses[-1].response
                assert result["status"] == "unavailable"
                assert "events" not in result
                assert result["error"]["code"] == "permission_required"
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[
                            types.Part(
                                text="Calendar access is unavailable. Run from the macOS Terminal app."
                            )
                        ],
                    )
                )

    settings = settings_at(tmp_path)
    store = Store(tmp_path)
    adapter = DeniedAdapter()
    agent = build_agent(settings, store, adapter)
    agent.model = PermissionModel()
    monkeypatch.setattr("migine.agent.build_agent", lambda *_args: agent)
    result = asyncio.run(chat(settings, store, adapter, "What events do I have today?", "denied"))
    assert "unavailable" in result


def test_mail_search_refreshes_empty_cache_and_reports_scope(tmp_path):
    class MailAdapter:
        def call(self, operation, payload):
            assert operation == "mail.read"
            assert payload["limit"] == 12
            assert payload["offset"] == 12
            return {
                "sources": [
                    {
                        "id": "live-test",
                        "title": "Invoice",
                        "body": "Synthetic receipt",
                        "received": "2026-10-24T00:00:00Z",
                        "url": "message://test",
                    }
                ],
                "partial": True,
                "skipped_batches": [{"offset": 13, "count": 1}],
                "scanned_positions": 12,
                "requested_positions": 12,
            }

    store = Store(tmp_path)
    agent = build_agent(settings_at(tmp_path), store, MailAdapter())
    tool = next(t for t in agent.tools if t.__name__ == "search_mail")
    result = tool("invoice", offset=12)
    assert result["sources"][0]["id"] == "live-test"
    assert result["scan"]["partial"] is True
    assert result["next_offset"] == 24
    assert "not all mail" in result["coverage"]


def test_mail_search_denial_does_not_claim_empty_inbox(tmp_path):
    class DeniedAdapter:
        def call(self, *_args):
            raise NativeToolError("mail.read", "permission_required")

    agent = build_agent(settings_at(tmp_path), Store(tmp_path), DeniedAdapter())
    tool = next(t for t in agent.tools if t.__name__ == "search_mail")
    result = tool("invoice")
    assert result["status"] == "unavailable"
    assert "Mail" in result["error"]["message"]
    assert "sources" not in result
