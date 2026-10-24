from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from claimcheck.agent import create_agent, run_agent
from claimcheck.config import Settings
from claimcheck.demo import fixture_root
from claimcheck.ollama import from_response, to_messages, to_tools
from claimcheck.tools import Audit


def test_native_adapter_message_and_tools() -> None:
    request = LlmRequest(
        contents=[
            types.Content(role="user", parts=[types.Part(text="audit")]),
            types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(
                            name="verify_claim",
                            args={"claim_id": "abc"},
                        )
                    )
                ],
            ),
            types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            name="verify_claim",
                            response={"status": "passed"},
                        )
                    )
                ],
            ),
        ],
        config=types.GenerateContentConfig(
            system_instruction="policy",
            tools=[
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name="verify_claim",
                            parameters=types.Schema(
                                type=types.Type.OBJECT,
                                properties={"claim_id": types.Schema(type=types.Type.STRING)},
                                required=["claim_id"],
                            ),
                        )
                    ]
                )
            ],
        ),
    )
    messages = to_messages(request)
    assert messages[0] == {"role": "system", "content": "policy"}
    assert messages[2]["tool_calls"][0]["function"]["arguments"] == {"claim_id": "abc"}
    assert messages[3]["role"] == "tool"
    assert json.loads(messages[3]["content"]) == {"status": "passed"}
    parameters = to_tools(request)[0]["function"]["parameters"]
    assert parameters["type"] == "object"
    assert parameters["properties"]["claim_id"]["type"] == "string"


def test_ollama_response_tool_calls() -> None:
    response = from_response(
        {
            "message": {
                "tool_calls": [
                    {
                        "function": {
                            "name": "verify_claim",
                            "arguments": '{"claim_id": "abc"}',
                        }
                    }
                ]
            },
            "prompt_eval_count": 2,
            "eval_count": 3,
        }
    )
    assert response.content is not None and response.content.parts
    assert response.content.parts[0].function_call.args == {"claim_id": "abc"}
    assert response.usage_metadata.total_token_count == 5
    with pytest.raises(ValueError, match="neither"):
        from_response({"message": {}})
    with pytest.raises(RuntimeError, match="rejected"):
        from_response({"error": "model missing"})


def test_full_adk_native_ollama_tool_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[dict] = []
    real_client = httpx.AsyncClient

    def respond(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            message = {
                "tool_calls": [
                    {
                        "function": {
                            "name": "verify_all_claims",
                            "arguments": {},
                        }
                    }
                ],
                "content": "",
            }
        else:
            assert any(message["role"] == "tool" for message in payload["messages"])
            message = {"content": "Found unsupported claims; inspect the evidence report."}
        return httpx.Response(
            200,
            json={
                "message": message,
                "prompt_eval_count": 10,
                "eval_count": 5,
            },
        )

    monkeypatch.setattr(
        "claimcheck.ollama.httpx.AsyncClient",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(respond)),
    )
    audit = Audit(fixture_root())
    result = asyncio.run(run_agent(audit, Settings()))
    assert result["transport"] == "ollama-native"
    assert result["tool_calls"] == ["verify_all_claims"]
    assert result["input_tokens"] == 20
    assert len(audit.ledger.results) == len(audit.ledger.claims)
    assert "litellm" not in type(create_agent(audit, Settings()).model).__module__


def test_remote_model_consent() -> None:
    with pytest.raises(ValueError, match="Remote"):
        Settings(base_url="http://example.com").validate()


@pytest.mark.parametrize("tool_loop", [False, True])
def test_agent_cannot_report_success_without_finishing(
    tool_loop: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_client = httpx.AsyncClient
    message = (
        {"tool_calls": [{"function": {"name": "list_claims", "arguments": {}}}]}
        if tool_loop
        else {"content": "Everything looks good without checking."}
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"message": message}))
    monkeypatch.setattr(
        "claimcheck.ollama.httpx.AsyncClient",
        lambda **kwargs: real_client(**kwargs, transport=transport),
    )
    audit = Audit(fixture_root())
    with pytest.raises(RuntimeError, match="limit|did not complete"):
        asyncio.run(run_agent(audit, Settings(max_calls=1)))
    assert all(result.status == "not_verified" for result in audit.ledger.complete())
