import asyncio
import json
import subprocess
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace

import anyio
import pytest
from mcp import ClientSession
from mcp.shared.memory import create_client_server_memory_streams

from pulseblr_events_mcp import gemini_client as bridge
from pulseblr_events_mcp.server import create_server
from pulseblr_events_mcp.sources import SampleSource

KEY = "AIzaFakeLocalFixtureOnly01234567890123"


class Bag(SimpleNamespace):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def model_dump_json(self):
        return json.dumps(self, default=lambda value: vars(value))


FAKE_TYPES = SimpleNamespace(
    Content=Bag,
    Part=Bag,
    FunctionDeclaration=Bag,
    FunctionResponse=Bag,
    GenerateContentConfig=Bag,
    Tool=Bag,
    AutomaticFunctionCallingConfig=Bag,
    ToolConfig=Bag,
    FunctionCallingConfig=Bag,
    ThinkingConfig=Bag,
)


def model_content(*calls, text=None):
    parts = [
        Bag(function_call=Bag(name=name, args=args, id=call_id)) for name, args, call_id in calls
    ]
    if text is not None:
        parts.append(Bag(text=text))
    return Bag(role="model", parts=parts, thought_signature=b"preserve-this-signature")


class FakeGemini:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.requests = []
        self.aio = Bag(models=Bag(generate_content=self.generate_content))

    async def generate_content(self, **kwargs):
        self.requests.append({**kwargs, "contents": list(kwargs["contents"])})
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        if callable(response):
            response = response(kwargs)
        return Bag(candidates=[Bag(content=response)])


@asynccontextmanager
async def sample_session():
    from datetime import datetime

    now = datetime.fromisoformat("2026-10-24T08:00:00+05:30")
    server = create_server(SampleSource(now=now), now=now)
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(
                server._lowlevel_server.run,
                *server_streams,
                server._lowlevel_server.create_initialization_options(),
            )
            async with ClientSession(*client_streams, read_timeout_seconds=20) as session:
                await session.initialize()
                yield session
            tasks.cancel_scope.cancel()


def run_turn(session, client, prompt="Find public engineering events", **kwargs):
    return bridge.run_turn(
        session, client, bridge.Settings(KEY), prompt=prompt, types_module=FAKE_TYPES, **kwargs
    )


def test_all_five_real_mcp_tools_preserve_content_and_function_ids():
    async def run():
        first = model_content(
            ("search_events", {"when": "weekend", "limit": 10}, "search-id"),
            ("list_topics", {"when": "weekend"}, "topics-id"),
        )
        second = []

        def follow_up(request):
            result = request["contents"][-1].parts[0].function_response.response
            event_ids = [event["id"] for event in result["events"]][:10]
            second.append(
                model_content(
                    ("get_event", {"event_id": event_ids[0]}, "event-id"),
                    ("recommend_communities", {"event_ids": event_ids}, "community-id"),
                    ("plan_schedule", {"event_ids": event_ids, "max_events": 2}, "plan-id"),
                )
            )
            return second[0]

        client = FakeGemini(first, follow_up, model_content(text="Fictional sample results."))
        traces = []
        async with sample_session() as session:
            result = await run_turn(session, client, verify_all_tools=True, trace=traces.append)
        assert result.text == "Fictional sample results."
        assert result.successful_tools == bridge.TOOL_NAMES
        assert result.tool_calls == 5
        assert client.requests[1]["contents"][1] is first
        assert client.requests[2]["contents"][3] is second[0]
        returned = client.requests[1]["contents"][2].parts
        assert [part.function_response.id for part in returned] == ["search-id", "topics-id"]
        assert returned[0].function_response.response["data_mode"] == "sample"
        assert (
            client.requests[2]["contents"][4].parts[0].function_response.response["found"] is True
        )
        config = client.requests[0]["config"]
        assert config.automatic_function_calling.disable is True
        assert config.automatic_continuation is False
        assert config.thinking_config.thinking_level == "low"
        assert config.tool_config.function_calling_config.mode == "AUTO"
        assert {item.name for item in config.tools[0].function_declarations} == bridge.TOOL_NAMES
        assert KEY not in repr(client.requests)
        assert any("search_events" in line for line in traces)
        assert "event_ids" not in " ".join(traces)

    asyncio.run(run())


def test_settings_read_only_explicit_simple_file(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "process-key-should-not-win-01234567890")
    monkeypatch.setenv("GEMINI_MODEL", "ambient-model-must-not-win")
    file = tmp_path / "manual.env"
    file.write_text(f'# Public manual setup\nGEMINI_API_KEY="{KEY}"\nGEMINI_MODEL=gemini-test\n')
    settings = bridge.load_settings(file)
    assert settings.api_key == KEY
    assert settings.model == "gemini-test"
    assert KEY not in repr(settings)
    assert bridge.load_settings(file, model_override="override").model == "override"
    assert bridge.load_settings(environ={"GEMINI_API_KEY": KEY}).model == bridge.DEFAULT_MODEL
    assert bridge.DEFAULT_MODEL == "gemini-3.5-flash-lite"


@pytest.mark.parametrize(
    "body",
    [
        "GEMINI_API_KEY=\n",
        "GEMINI_API_KEY=your-key-here\n",
        f"GEMINI_API_KEY={KEY}\nGEMINI_API_KEY={KEY}\n",
        f"GEMINI_API_KEY={KEY}\nOTHER_SETTING=bad\n",
        f"export GEMINI_API_KEY={KEY}\n",
        f"GEMINI_API_KEY=space {KEY}\n",
    ],
)
def test_settings_reject_malformed_unknown_duplicate_or_placeholder_files(tmp_path, body):
    file = tmp_path / "test.env"
    file.write_text(body)
    with pytest.raises(bridge.ClientError) as error:
        bridge.load_settings(file)
    assert KEY not in str(error.value)


def test_child_env_never_inherits_credentials_or_python_path():
    child = bridge.safe_child_environment(
        {
            "PATH": "safe-path",
            "SYSTEMROOT": "C:/Windows",
            "TEMP": "C:/Temp",
            "GEMINI_API_KEY": KEY,
            "GOOGLE_API_KEY": KEY,
            "PYTHONPATH": "untrusted-code",
            "HTTPS_PROXY": "http://proxy.invalid",
            "APPDATA": KEY,
        },
        api_key=KEY,
    )
    assert child["PATH"] == "safe-path"
    assert KEY not in repr(child)
    assert "PYTHONPATH" not in child
    assert "GEMINI_API_KEY" not in child and "HTTPS_PROXY" not in child


def test_settings_accept_printable_provider_keys_with_dots_without_format_assumptions():
    key = "example.fake.credential.1234567890"
    settings = bridge.load_settings(environ={"GEMINI_API_KEY": key})
    assert settings.api_key == key
    assert key not in repr(settings)


def test_user_key_is_refused_before_any_model_request():
    async def run():
        client = FakeGemini()
        with pytest.raises(bridge.ClientError, match="credential"):
            await run_turn(None, client, prompt=f"Show {KEY}")
        assert client.requests == []

    asyncio.run(run())


def test_undeclared_tool_is_blocked_without_dispatch():
    async def run():
        client = FakeGemini(model_content(("run_shell", {"command": "no"}, "bad")))
        async with sample_session() as session:
            with pytest.raises(bridge.ClientError, match="unavailable tool"):
                await run_turn(session, client)
        assert len(client.requests) == 1

    asyncio.run(run())


def test_model_round_and_tool_call_limits():
    async def run():
        calls = model_content(("list_topics", {}, "repeat"))
        async with sample_session() as session:
            client = FakeGemini(calls, calls)
            with pytest.raises(bridge.ClientError, match="round limit"):
                await run_turn(session, client, max_rounds=2)
            assert len(client.requests) == 2
            client = FakeGemini(model_content(*[("list_topics", {}, str(i)) for i in range(3)]))
            with pytest.raises(bridge.ClientError, match="tool-call limit"):
                await run_turn(session, client, max_tool_calls=2)

    asyncio.run(run())


def test_tool_error_and_missing_structured_content_are_explicit_not_success():
    async def run():
        class Session:
            async def list_tools(self):
                return Bag(
                    tools=[
                        Bag(name=name, description=name, input_schema={"type": "object"})
                        for name in bridge.TOOL_NAMES
                    ]
                )

            async def call_tool(self, name, args):
                return Bag(
                    is_error=name == "get_event",
                    structured_content=None,
                    content=[Bag(text=f"private error {KEY}")],
                )

        client = FakeGemini(
            model_content(("get_event", {}, "bad"), ("list_topics", {}, "missing")),
            model_content(text=f"A model echo {KEY}"),
        )
        result = await run_turn(Session(), client)
        assert result.successful_tools == frozenset()
        assert KEY not in result.text
        assert KEY not in repr(client.requests)
        parts = client.requests[1]["contents"][2].parts
        assert all("error" in part.function_response.response for part in parts)

    asyncio.run(run())


def test_verify_requires_all_successful_tools_and_prompt_size_is_bounded():
    async def run():
        async with sample_session() as session:
            with pytest.raises(bridge.ClientError, match="every MCP tool"):
                await run_turn(
                    session,
                    FakeGemini(model_content(text="I checked everything.")),
                    verify_all_tools=True,
                )
        with pytest.raises(bridge.ClientError, match="8000"):
            await run_turn(None, FakeGemini(), prompt="x" * 8001)

    asyncio.run(run())


def test_quota_errors_are_actionable_and_never_echo_raw_exception():
    async def run():
        error = RuntimeError(f"Raw body secret {KEY}")
        error.code = 429
        client = FakeGemini(error)
        async with sample_session() as session:
            with pytest.raises(bridge.ClientError, match="quota") as caught:
                await run_turn(session, client)
        assert KEY not in str(caught.value) and "Raw body" not in str(caught.value)

    asyncio.run(run())


def test_tool_arguments_containing_key_never_reach_mcp():
    async def run():
        client = FakeGemini(model_content(("search_events", {"query": KEY}, "unsafe")))
        async with sample_session() as session:
            with pytest.raises(bridge.ClientError, match="credential"):
                await run_turn(session, client)
        assert len(client.requests) == 1

    asyncio.run(run())


def test_fixed_official_api_transport_cannot_inherit_proxy_or_provider_routing(monkeypatch):
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return "fake-client"

    types = Bag(HttpOptions=Bag, HttpRetryOptions=Bag)
    monkeypatch.setattr(bridge, "_load_sdk", lambda: (Bag(Client=create), types))
    transport = object()
    monkeypatch.setattr(bridge, "_new_async_http_client", lambda: transport)
    client, _, owned_transport = bridge.create_gemini_client(bridge.Settings(KEY))
    assert client == "fake-client"
    assert owned_transport is transport
    assert captured["vertexai"] is False and captured["enterprise"] is False
    assert captured["api_key"] == KEY
    options = captured["http_options"]
    assert options.base_url == "https://generativelanguage.googleapis.com"
    assert options.timeout == 60000
    assert options.client_args == {"trust_env": False}
    assert options.async_client_args == {"trust_env": False}
    assert options.retry_options.attempts == 1
    assert options.httpx_async_client is transport


def test_real_sdk_cannot_switch_to_proxy_inheriting_aiohttp_transport():
    pytest.importorskip("google.genai")

    async def run():
        client, _, transport = bridge.create_gemini_client(bridge.Settings(KEY))
        try:
            assert client._api_client._use_aiohttp() is False
            assert transport.trust_env is False
            assert transport.follow_redirects is False
        finally:
            await client.aio.aclose()
            await transport.aclose()
            client.close()

    asyncio.run(run())


def test_help_works_without_site_packages_or_optional_sdk():
    completed = subprocess.run(
        [sys.executable, "-S", "-m", "pulseblr_events_mcp.gemini_client", "--help"],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=__import__("pathlib").Path(__file__).resolve().parents[1],
        env=bridge.safe_child_environment(api_key=KEY),
    )
    assert completed.returncode == 0
    assert "--verify-all-tools" in completed.stdout
    assert "Traceback" not in completed.stderr


def test_real_sdk_accepts_mcp_schemas_and_preserves_function_response_id():
    types = pytest.importorskip("google.genai.types")

    async def run():
        content = types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(name="list_topics", args={}, id="real-sdk-id"),
                    thought_signature=b"signature-to-preserve",
                )
            ],
        )
        answer = types.Content(role="model", parts=[types.Part(text="Fictional sample topics.")])
        client = FakeGemini(content, answer)
        async with sample_session() as session:
            result = await bridge.run_turn(
                session,
                client,
                bridge.Settings(KEY),
                prompt="Find public topics",
                types_module=types,
            )
        assert result.successful_tools == {"list_topics"}
        assert client.requests[1]["contents"][1] is content
        returned = client.requests[1]["contents"][2].parts[0].function_response
        assert returned.id == "real-sdk-id"
        assert returned.response["data_mode"] == "sample"
        assert client.requests[0]["config"].automatic_continuation is False

    asyncio.run(run())


def test_quota_error_remains_actionable_through_stdio_exception_group(capsys, monkeypatch):
    monkeypatch.setattr(bridge, "load_settings", lambda *args, **kwargs: bridge.Settings(KEY))

    async def fail(*args):
        raise ExceptionGroup("raw transport detail", [bridge.ClientError("Gemini quota reached.")])

    monkeypatch.setattr(bridge, "_run_cli", fail)
    assert bridge.main(["--prompt", "Public event query"]) == 1
    stderr = capsys.readouterr().err
    assert "Gemini quota reached." in stderr
    assert "raw transport detail" not in stderr


@pytest.mark.parametrize(
    "payload, expected",
    [
        ({"events": [{"title": "x" * 64000}]}, "64000"),
        ({"events": [{"title": KEY}]}, "credential"),
    ],
)
def test_unsafe_tool_results_never_go_back_to_google(payload, expected):
    async def run():
        class Session:
            async def list_tools(self):
                return Bag(
                    tools=[
                        Bag(name=name, description=name, input_schema={"type": "object"})
                        for name in bridge.TOOL_NAMES
                    ]
                )

            async def call_tool(self, name, args):
                return Bag(is_error=False, structured_content=payload)

        client = FakeGemini(model_content(("search_events", {}, "result-id")))
        with pytest.raises(bridge.ClientError, match=expected):
            await run_turn(Session(), client)
        assert len(client.requests) == 1

    asyncio.run(run())


def test_interactive_history_preserves_public_context_and_bounds_whole_turns():
    async def run():
        history = bridge.ConversationHistory()
        first = model_content(("list_topics", {}, "topics"))
        client = FakeGemini(
            first,
            model_content(text="Sample topics include AI."),
            *[model_content(text="Public follow-up answer.") for _ in range(12)],
        )
        async with sample_session() as session:
            await run_turn(session, client, history=history)
            await run_turn(
                session, client, prompt="Which of those topics is observed?", history=history
            )
            assert client.requests[2]["contents"][1] is first
            assert "Sample topics include AI." in repr(client.requests[2]["contents"])
            for _ in range(11):
                await run_turn(
                    session, client, prompt="Continue with public events", history=history
                )
        assert len(history.contents()) <= 20
        assert all(turn[0].role == "user" and turn[-1].role == "model" for turn in history.turns)
        assert KEY not in repr(history)

    asyncio.run(run())


def test_gateway_timeout_maps_to_provider_error_without_blame_on_key_or_mcp():
    error = RuntimeError(f"secret transport body {KEY}")
    error.code = 504
    assert bridge.safe_error(error) == (
        "Gemini gateway timed out. Retry later or select another available model with --model."
    )


def test_model_override_does_not_receive_unsupported_gemini3_thinking_settings():
    async def run():
        client = FakeGemini(model_content(text="Public response."))
        async with sample_session() as session:
            await bridge.run_turn(
                session,
                client,
                bridge.Settings(KEY, "gemini-2.5-flash"),
                prompt="Find public events",
                types_module=FAKE_TYPES,
            )
        assert client.requests[0]["config"].thinking_config is None

    asyncio.run(run())


def test_recursive_secret_check_uses_raw_strings_before_json_escaping():
    key = 'fixture.key."quoted"\\path.123456789'

    class ModelDumpOnly:
        __slots__ = ()

        def model_dump(self, *, mode):
            assert mode == "python"
            return {"nested": [f"prefix {key} suffix"]}

    values = [
        {"nested": [{"message": key}]},
        {key: "a credential can also appear in a mapping key"},
        Bag(metadata=(Bag(text=key),)),
        ModelDumpOnly(),
    ]
    assert all(bridge.contains_secret(value, key) for value in values)
    assert not bridge.contains_secret({"events": ["public event"]}, key)
    cycle = {}
    cycle["cycle"] = cycle
    assert not bridge.contains_secret(cycle, key)


def test_escaped_key_in_nested_result_is_blocked_before_google_or_history():
    async def run():
        key = 'fixture.key."quoted"\\path.123456789'
        settings = bridge.load_settings(environ={"GEMINI_API_KEY": key})
        history = bridge.ConversationHistory()

        class Session:
            async def list_tools(self):
                return Bag(
                    tools=[
                        Bag(name=name, description=name, input_schema={"type": "object"})
                        for name in bridge.TOOL_NAMES
                    ]
                )

            async def call_tool(self, name, args):
                return Bag(is_error=False, structured_content={"events": [{"metadata": [key]}]})

        client = FakeGemini(model_content(("search_events", {}, "result-id")))
        with pytest.raises(bridge.ClientError, match="credential"):
            await bridge.run_turn(
                Session(),
                client,
                settings,
                prompt="Find public events",
                types_module=FAKE_TYPES,
                history=history,
            )
        assert len(client.requests) == 1
        assert history.contents() == []

    asyncio.run(run())


def test_escaped_key_in_final_model_text_is_redacted_and_not_kept_in_history():
    async def run():
        key = 'fixture.key."quoted"\\path.123456789'
        history = bridge.ConversationHistory()
        client = FakeGemini(model_content(text=f"An unwanted credential echo {key}"))
        async with sample_session() as session:
            result = await bridge.run_turn(
                session,
                client,
                bridge.Settings(key),
                prompt="Find public events",
                types_module=FAKE_TYPES,
                history=history,
            )
        assert key not in result.text
        assert history.contents() == []

    asyncio.run(run())


def test_posix_inherited_os_names_are_explicitly_sanitized():
    child = bridge.safe_child_environment(
        {
            "HOME": f"/home/{KEY}",
            "USER": "public-user",
            "LOGNAME": "public-user",
            "SHELL": "/bin/sh",
            "TERM": "xterm",
        },
        api_key=KEY,
    )
    assert child["HOME"] == ""
    assert child["USER"] == "public-user"
    assert child["LOGNAME"] == "public-user"
    assert child["SHELL"] == "/bin/sh"
    assert child["TERM"] == "xterm"
    assert KEY not in repr(child)
