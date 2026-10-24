"""Offline tests for the ADK agent, tools, and generation error mapping."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest
from google.adk.agents import LlmAgent
from google.adk.agents.invocation_context import LlmCallsLimitExceededError
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.models.registry import LLMRegistry
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import Field

from pr_draft_agent import agent as agent_module
from pr_draft_agent.agent import GenerationError, build_agent, generate_draft
from pr_draft_agent.repository import ChangedFile, RepositorySnapshot


def _snapshot(
    root: Path,
    *,
    diff: str = "+change\n",
    template: str = "## Summary\n\n## Testing\n",
    template_source: str | None = ".github/PULL_REQUEST_TEMPLATE.md",
) -> RepositorySnapshot:
    return RepositorySnapshot(
        root=root,
        files=(ChangedFile("src/app.py", "100644", "100644", "M"),),
        diff=diff,
        diff_sha256=hashlib.sha256(diff.encode("utf-8")).hexdigest(),
        template=template,
        template_source=template_source,
    )


def _part(text: str, *, thought: bool = False) -> SimpleNamespace:
    return SimpleNamespace(text=text, thought=thought)


class FakeEvent:
    def __init__(
        self,
        parts: list[SimpleNamespace] | None = None,
        *,
        final: bool = True,
        error_code: str | None = None,
        finish_reason: object | None = None,
    ) -> None:
        self.content = SimpleNamespace(parts=parts) if parts is not None else None
        self.error_code = error_code
        self.finish_reason = finish_reason
        self._final = final

    def is_final_response(self) -> bool:
        return self._final


class ScriptedLlm(BaseLlm):
    """A deterministic local model used to exercise the real ADK runner."""

    script: list[LlmResponse] = Field(default_factory=list)
    call_index: int = 0
    requests: list[object] = Field(default_factory=list)

    async def generate_content_async(self, llm_request: object, stream: bool = False):
        self.requests.append(llm_request)
        index = self.call_index
        self.call_index += 1
        if index < len(self.script):
            yield self.script[index]


def _install_fake_runner(
    monkeypatch: pytest.MonkeyPatch,
    *,
    events: list[FakeEvent] | None = None,
    tool_count: int = 2,
    error: Exception | None = None,
) -> type:
    events = events or []

    class FakeRunner:
        instances: ClassVar[list[FakeRunner]] = []

        def __init__(self, *, app_name: str, agent: LlmAgent, session_service: object):
            self.app_name = app_name
            self.agent = agent
            self.session_service = session_service
            self.session_id: str | None = None
            self.run_config: object | None = None
            self.new_message: object | None = None
            self.closed = False
            self.tool_payloads: list[dict] = []
            FakeRunner.instances.append(self)

        async def run_async(
            self,
            *,
            user_id: str,
            session_id: str,
            new_message: object,
            run_config: object,
        ):
            self.session_id = session_id
            self.new_message = new_message
            self.run_config = run_config
            for tool in self.agent.tools[:tool_count]:
                self.tool_payloads.append(tool())
            if error is not None:
                raise error
            for event in events:
                yield event

        async def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(agent_module, "Runner", FakeRunner)
    return FakeRunner


def test_build_agent_has_two_no_argument_tools(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path / "repo", diff="+DIFF_SENTINEL", template="TEMPLATE_SENTINEL")
    used_tools: set[str] = set()

    built = build_agent(snapshot, "gemini-test", used_tools)

    assert isinstance(built, LlmAgent)
    assert built.name.isidentifier()
    assert [tool.__name__ for tool in built.tools] == [
        "get_staged_diff",
        "get_pr_template",
    ]
    for tool in built.tools:
        assert inspect.signature(tool).parameters == {}

    resolved = asyncio.run(built.canonical_tools())
    assert [tool.name for tool in resolved] == ["get_staged_diff", "get_pr_template"]
    for tool in resolved:
        declaration = tool._get_declaration()
        assert declaration is not None
        assert declaration.parameters is None

    diff_payload = built.tools[0]()
    template_payload = built.tools[1]()

    assert diff_payload == {
        "scope": "staged",
        "files": [{"path": "src/app.py", "status": "M"}],
        "diff": "+DIFF_SENTINEL",
        "diff_sha256": hashlib.sha256(b"+DIFF_SENTINEL").hexdigest(),
    }
    assert template_payload == {
        "source": ".github/PULL_REQUEST_TEMPLATE.md",
        "content": "TEMPLATE_SENTINEL",
        "fallback": False,
    }
    assert used_tools == {"get_staged_diff", "get_pr_template"}
    assert str(snapshot.root) not in json.dumps(diff_payload)
    assert str(snapshot.root) not in json.dumps(template_payload)

    assert built.generate_content_config.max_output_tokens == 4096
    instruction = built.instruction
    assert "get_staged_diff" in instruction
    assert "get_pr_template" in instruction
    assert "untrusted" in instruction.lower()
    assert "comments" in instruction.lower()
    assert "author-provided intent" in instruction.lower()
    assert "# <title>" in instruction
    assert "unchecked" in instruction.lower()
    assert "absolute" in instruction.lower()
    assert "Motivation not provided." in instruction
    assert "DIFF_SENTINEL" not in instruction
    assert "TEMPLATE_SENTINEL" not in instruction


def test_tools_repeat_and_template_fallback(tmp_path: Path) -> None:
    with_source = _snapshot(tmp_path / "with-source")
    used_tools: set[str] = set()
    built = build_agent(with_source, "gemini-test", used_tools)

    first_diff = built.tools[0]()
    second_diff = built.tools[0]()
    first_template = built.tools[1]()
    second_template = built.tools[1]()

    assert first_diff == second_diff
    assert first_template == second_template
    assert first_template["source"] == ".github/PULL_REQUEST_TEMPLATE.md"
    assert first_template["fallback"] is False
    assert used_tools == {"get_staged_diff", "get_pr_template"}

    without_source = _snapshot(tmp_path / "without-source", template_source=None)
    fallback_agent = build_agent(without_source, "gemini-test", set())
    fallback_payload = fallback_agent.tools[1]()
    assert fallback_payload["source"] is None
    assert fallback_payload["fallback"] is True
    assert fallback_payload["content"] == "## Summary\n\n## Testing\n"


def test_generate_draft_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path / "repo", diff="+DIFF_ONLY")
    events = [
        FakeEvent([_part("INTERMEDIATE")], final=False),
        FakeEvent(
            [
                _part("internal reasoning", thought=True),
                _part("\n# Add config error\n\n## Summary\n\nBody\n"),
            ],
            finish_reason=types.FinishReason.STOP,
        ),
    ]
    fake_runner = _install_fake_runner(monkeypatch, events=events)

    text = asyncio.run(generate_draft(snapshot, "Fix missing configuration errors", "gemini-test"))

    assert text == "# Add config error\n\n## Summary\n\nBody"
    assert "INTERMEDIATE" not in text
    runner = fake_runner.instances[0]
    assert runner.closed is True
    assert runner.session_id
    config = runner.run_config
    assert config.max_llm_calls == 5
    assert config.http_options.timeout == 30_000
    assert config.http_options.retry_options.attempts == 2
    assert config.http_options.retry_options.initial_delay == 0.5
    assert config.http_options.retry_options.max_delay == 2.0
    assert runner.agent.generate_content_config.max_output_tokens == 4096
    assert "Fix missing configuration errors" not in runner.agent.instruction
    assert "AUTHOR-PROVIDED INTENT (BEGIN)" in runner.new_message.parts[0].text
    assert "Fix missing configuration errors" in runner.new_message.parts[0].text
    assert "AUTHOR-PROVIDED INTENT (END)" in runner.new_message.parts[0].text
    assert len(runner.tool_payloads) == 2
    assert "+DIFF_ONLY" not in runner.new_message.parts[0].text
    assert "## Summary" not in runner.new_message.parts[0].text


def test_intent_is_labeled_in_the_user_message_not_the_system_prompt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_runner = _install_fake_runner(monkeypatch, events=[FakeEvent([_part("# Title\n\nBody")])])
    intent = "Explain {missing_state} literally without state injection"

    asyncio.run(generate_draft(_snapshot(tmp_path / "repo"), intent, "gemini-test"))
    with_intent = fake_runner.instances[0]

    asyncio.run(generate_draft(_snapshot(tmp_path / "other"), "", "gemini-test"))
    without_intent = fake_runner.instances[1]

    message = with_intent.new_message.parts[0].text
    assert "AUTHOR-PROVIDED INTENT (BEGIN)" in message
    assert intent in message
    assert "AUTHOR-PROVIDED INTENT (END)" in message
    assert intent not in with_intent.agent.instruction
    assert "No author intent was provided." in without_intent.new_message.parts[0].text


def test_real_adk_runner_executes_both_tools(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scripted = ScriptedLlm(
        model="scripted-model",
        script=[
            LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(name="get_staged_diff", args={})
                        ),
                        types.Part(
                            function_call=types.FunctionCall(name="get_pr_template", args={})
                        ),
                    ],
                )
            ),
            LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text="# Title\n\nBody")]),
                finish_reason=types.FinishReason.STOP,
            ),
        ],
    )
    monkeypatch.setattr(LLMRegistry, "new_llm", staticmethod(lambda model: scripted))

    text = asyncio.run(
        generate_draft(_snapshot(tmp_path / "repo"), "demo intent", "scripted-model")
    )

    assert text == "# Title\n\nBody"
    assert scripted.call_index == 2


def test_real_adk_runner_rejects_a_model_that_skips_tools(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scripted = ScriptedLlm(
        model="scripted-model",
        script=[
            LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text="# Title\n\nBody")]),
                finish_reason=types.FinishReason.STOP,
            )
        ],
    )
    monkeypatch.setattr(LLMRegistry, "new_llm", staticmethod(lambda model: scripted))

    with pytest.raises(GenerationError) as excinfo:
        asyncio.run(generate_draft(_snapshot(tmp_path / "repo"), "", "scripted-model"))

    assert excinfo.value.code == "TOOLS_NOT_USED"
    assert scripted.call_index == 1


def test_generate_draft_requires_both_tools(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_runner = _install_fake_runner(
        monkeypatch,
        tool_count=1,
        events=[FakeEvent([_part("# Title\n\nBody")])],
    )

    with pytest.raises(GenerationError) as excinfo:
        asyncio.run(generate_draft(_snapshot(tmp_path / "repo"), "", "gemini-test"))

    assert excinfo.value.code == "TOOLS_NOT_USED"
    assert fake_runner.instances[0].closed is True


def test_generate_draft_rejects_missing_final_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_runner = _install_fake_runner(
        monkeypatch,
        events=[FakeEvent([_part("only reasoning", thought=True)])],
    )

    with pytest.raises(GenerationError) as excinfo:
        asyncio.run(generate_draft(_snapshot(tmp_path / "repo"), "", "gemini-test"))

    assert excinfo.value.code == "INVALID_DRAFT"
    assert "only reasoning" not in str(excinfo.value)
    assert fake_runner.instances[0].closed is True


def test_generate_draft_rejects_no_events(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_runner = _install_fake_runner(monkeypatch, events=[])

    with pytest.raises(GenerationError) as excinfo:
        asyncio.run(generate_draft(_snapshot(tmp_path / "repo"), "", "gemini-test"))

    assert excinfo.value.code == "INVALID_DRAFT"
    assert fake_runner.instances[0].closed is True


def test_generate_draft_rejects_error_event(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_runner = _install_fake_runner(
        monkeypatch,
        events=[
            FakeEvent([_part("# Partial\n\nBody")], error_code="MAX_TOKENS"),
        ],
    )

    with pytest.raises(GenerationError) as excinfo:
        asyncio.run(generate_draft(_snapshot(tmp_path / "repo"), "", "gemini-test"))

    assert excinfo.value.code == "PROVIDER_ERROR"
    assert "Partial" not in str(excinfo.value)
    assert fake_runner.instances[0].closed is True


def test_generate_draft_rejects_truncated_final_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_runner = _install_fake_runner(
        monkeypatch,
        events=[
            FakeEvent(
                [_part("# Partial\n\nBody")],
                finish_reason=types.FinishReason.MAX_TOKENS,
            ),
        ],
    )

    with pytest.raises(GenerationError) as excinfo:
        asyncio.run(generate_draft(_snapshot(tmp_path / "repo"), "", "gemini-test"))

    assert excinfo.value.code == "PROVIDER_ERROR"
    assert "Partial" not in str(excinfo.value)
    assert fake_runner.instances[0].closed is True


def test_generate_draft_maps_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_runner = _install_fake_runner(monkeypatch, error=TimeoutError("raw timeout sk-secret"))

    with pytest.raises(GenerationError) as excinfo:
        asyncio.run(generate_draft(_snapshot(tmp_path / "repo"), "", "gemini-test"))

    assert excinfo.value.code == "MODEL_TIMEOUT"
    assert "raw timeout" not in str(excinfo.value)
    assert "sk-secret" not in str(excinfo.value)
    assert fake_runner.instances[0].closed is True


@pytest.mark.parametrize(
    ("status", "expected_code", "error_type"),
    [
        (400, "PROVIDER_ERROR", genai_errors.ClientError),
        (401, "AUTH_FAILED", genai_errors.ClientError),
        (403, "AUTH_FAILED", genai_errors.ClientError),
        (429, "RATE_LIMITED", genai_errors.ClientError),
        (404, "MODEL_UNAVAILABLE", genai_errors.ClientError),
        (500, "MODEL_UNAVAILABLE", genai_errors.ServerError),
    ],
)
def test_generate_draft_maps_provider_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    status: int,
    expected_code: str,
    error_type: type[genai_errors.APIError],
) -> None:
    error = error_type(status, {"error": {"message": "leaked sk-secret body"}})
    fake_runner = _install_fake_runner(monkeypatch, error=error)

    with pytest.raises(GenerationError) as excinfo:
        asyncio.run(generate_draft(_snapshot(tmp_path / "repo"), "", "gemini-test"))

    assert excinfo.value.code == expected_code
    assert "sk-secret" not in str(excinfo.value)
    assert "leaked" not in str(excinfo.value)
    assert fake_runner.instances[0].closed is True


def test_generate_draft_maps_call_limit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_runner = _install_fake_runner(
        monkeypatch, error=LlmCallsLimitExceededError("raw call limit")
    )

    with pytest.raises(GenerationError) as excinfo:
        asyncio.run(generate_draft(_snapshot(tmp_path / "repo"), "", "gemini-test"))

    assert excinfo.value.code == "CALL_LIMIT"
    assert "raw call limit" not in str(excinfo.value)
    assert fake_runner.instances[0].closed is True


def test_generate_draft_maps_unexpected_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_runner = _install_fake_runner(monkeypatch, error=RuntimeError("raw prompt sk-secret"))

    with pytest.raises(GenerationError) as excinfo:
        asyncio.run(generate_draft(_snapshot(tmp_path / "repo"), "", "gemini-test"))

    assert excinfo.value.code == "AGENT_FAILED"
    assert "raw prompt" not in str(excinfo.value)
    assert "sk-secret" not in str(excinfo.value)
    assert fake_runner.instances[0].closed is True


def test_sessions_and_tools_are_isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_runner = _install_fake_runner(monkeypatch, events=[FakeEvent([_part("# Title\n\nBody")])])
    first_snapshot = _snapshot(tmp_path / "first", diff="+FIRST_ONLY", template="FIRST_TEMPLATE")
    second_snapshot = _snapshot(
        tmp_path / "second", diff="+SECOND_ONLY", template="SECOND_TEMPLATE"
    )

    asyncio.run(generate_draft(first_snapshot, "first intent", "gemini-test"))
    asyncio.run(generate_draft(second_snapshot, "second intent", "gemini-test"))

    first, second = fake_runner.instances
    assert first is not second
    assert first.session_service is not second.session_service
    assert first.session_id != second.session_id
    assert first.tool_payloads[0]["diff"] == "+FIRST_ONLY"
    assert second.tool_payloads[0]["diff"] == "+SECOND_ONLY"
    assert "FIRST_ONLY" not in second.tool_payloads[0]["diff"]
    assert first.tool_payloads[1]["content"] == "FIRST_TEMPLATE"
    assert second.tool_payloads[1]["content"] == "SECOND_TEMPLATE"
    assert "first intent" in first.new_message.parts[0].text
    assert "first intent" not in second.new_message.parts[0].text
    assert first.closed is True
    assert second.closed is True


def test_real_adk_runner_passes_bounds_to_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scripted = ScriptedLlm(
        model="scripted-model",
        script=[
            LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text="# Title\n\nBody")]),
                finish_reason=types.FinishReason.STOP,
            )
        ],
    )
    monkeypatch.setattr(LLMRegistry, "new_llm", staticmethod(lambda model: scripted))

    with pytest.raises(GenerationError, match="both required snapshot tools"):
        asyncio.run(generate_draft(_snapshot(tmp_path), "", "scripted-model"))

    config = scripted.requests[0].config
    assert config.max_output_tokens == 4096
    assert config.http_options.timeout == 30_000
    assert config.http_options.retry_options.attempts == 2


def test_real_adk_runner_stops_repeated_tool_calls(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tool_request = LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part(function_call=types.FunctionCall(name="get_staged_diff", args={}))],
        )
    )
    scripted = ScriptedLlm(model="scripted-model", script=[tool_request] * 7)
    monkeypatch.setattr(LLMRegistry, "new_llm", staticmethod(lambda model: scripted))

    with pytest.raises(GenerationError) as excinfo:
        asyncio.run(generate_draft(_snapshot(tmp_path), "", "scripted-model"))

    assert excinfo.value.code == "CALL_LIMIT"
    assert scripted.call_index == 5


@pytest.mark.parametrize("external_cancel", [False, True])
def test_timeout_and_cancellation_close_runner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, external_cancel: bool
) -> None:
    fake_runner = _install_fake_runner(monkeypatch)
    entered = asyncio.Event()
    cancelled = []

    async def hanging_run(self, **kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)
        yield  # Make this a streaming async generator.

    monkeypatch.setattr(fake_runner, "run_async", hanging_run)
    monkeypatch.setattr(agent_module, "_TIMEOUT_SECONDS", 0.02)

    async def exercise():
        task = asyncio.create_task(generate_draft(_snapshot(tmp_path), "", "gemini-test"))
        await entered.wait()
        if external_cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(GenerationError) as excinfo:
                await task
            assert excinfo.value.code == "MODEL_TIMEOUT"

    asyncio.run(exercise())
    assert cancelled == [True]
    assert fake_runner.instances[0].closed is True


def test_generation_logs_exclude_source_and_exception_bodies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _install_fake_runner(monkeypatch, error=RuntimeError("PRIVATE_EXCEPTION"))
    caplog.set_level("INFO", logger="pr_draft_agent.agent")

    with pytest.raises(GenerationError):
        asyncio.run(
            generate_draft(
                _snapshot(tmp_path, diff="PRIVATE_DIFF", template="PRIVATE_TEMPLATE"),
                "PRIVATE_INTENT",
                "gemini-test",
            )
        )

    for sensitive in ("PRIVATE_EXCEPTION", "PRIVATE_DIFF", "PRIVATE_TEMPLATE", "PRIVATE_INTENT"):
        assert sensitive not in caplog.text


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("UNAUTHENTICATED", "AUTH_FAILED"),
        ("PERMISSION_DENIED", "AUTH_FAILED"),
        ("RESOURCE_EXHAUSTED", "RATE_LIMITED"),
        ("NOT_FOUND", "MODEL_UNAVAILABLE"),
        ("UNAVAILABLE", "MODEL_UNAVAILABLE"),
        ("INTERNAL", "MODEL_UNAVAILABLE"),
        ("DEADLINE_EXCEEDED", "MODEL_TIMEOUT"),
    ],
)
def test_real_adk_runner_maps_wrapped_provider_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, status: str, expected: str
) -> None:
    class FailingLlm(BaseLlm):
        async def generate_content_async(self, llm_request, stream=False):
            raise genai_errors.ClientError(
                400, {"error": {"status": status, "message": "PRIVATE_PROVIDER_BODY"}}
            )
            yield

    scripted = FailingLlm(model="scripted-model")
    monkeypatch.setattr(LLMRegistry, "new_llm", staticmethod(lambda model: scripted))

    with pytest.raises(GenerationError) as excinfo:
        asyncio.run(generate_draft(_snapshot(tmp_path), "", "scripted-model"))

    assert excinfo.value.code == expected
    assert "PRIVATE_PROVIDER_BODY" not in str(excinfo.value)


def test_real_adk_runner_maps_wrapped_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class FailingLlm(BaseLlm):
        async def generate_content_async(self, llm_request, stream=False):
            raise TimeoutError("PRIVATE_TIMEOUT_BODY")
            yield

    scripted = FailingLlm(model="scripted-model")
    monkeypatch.setattr(LLMRegistry, "new_llm", staticmethod(lambda model: scripted))
    with pytest.raises(GenerationError) as excinfo:
        asyncio.run(generate_draft(_snapshot(tmp_path), "", "scripted-model"))
    assert excinfo.value.code == "MODEL_TIMEOUT"
    assert "PRIVATE_TIMEOUT_BODY" not in str(excinfo.value)
