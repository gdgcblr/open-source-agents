"""Native Ollama /api/chat transport for ADK. No LiteLLM dependency."""

from __future__ import annotations

import json
import ssl
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from claimcheck.safety import MAX_BYTES


def json_schema(value: Any) -> Any:
    if isinstance(value, list):
        return [json_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key == "type" and isinstance(item, str):
            result[key] = item.lower()
        else:
            result[key] = json_schema(item) if isinstance(item, (dict, list)) else item
    return result


def to_messages(request: LlmRequest) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if request.config and request.config.system_instruction:
        instruction = request.config.system_instruction
        if isinstance(instruction, str):
            text = instruction
        elif isinstance(instruction, types.Content):
            text = "\n".join(part.text or "" for part in instruction.parts or [])
        else:
            raise ValueError("Unsupported ADK system instruction type")
        messages.append({"role": "system", "content": text})
    for content in request.contents:
        text_parts: list[str] = []
        calls = []
        responses = []
        for part in content.parts or []:
            if part.text and not part.thought:
                text_parts.append(part.text)
            elif part.function_call:
                calls.append(
                    {
                        "type": "function",
                        "function": {
                            "name": part.function_call.name,
                            "arguments": part.function_call.args or {},
                        },
                    }
                )
            elif part.function_response:
                responses.append(
                    {
                        "role": "tool",
                        "tool_name": part.function_response.name,
                        "content": json.dumps(part.function_response.response),
                    }
                )
        if text_parts or calls:
            message: dict[str, Any] = {
                "role": "assistant" if content.role == "model" else "user",
                "content": "\n".join(text_parts),
            }
            if calls:
                message["tool_calls"] = calls
            messages.append(message)
        messages.extend(responses)
    return messages


def to_tools(request: LlmRequest) -> list[dict[str, Any]]:
    tools = []
    for tool in (request.config.tools if request.config else None) or []:
        if not isinstance(tool, types.Tool):
            raise ValueError("Only ADK function tools are supported")
        for function in tool.function_declarations or []:
            parameters = function.parameters_json_schema
            if parameters is None and function.parameters is not None:
                parameters = json_schema(
                    function.parameters.model_dump(mode="json", exclude_none=True, by_alias=True)
                )
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": function.name,
                        "description": function.description or "",
                        "parameters": parameters or {"type": "object", "properties": {}},
                    },
                }
            )
    return tools


def from_response(data: dict[str, Any]) -> LlmResponse:
    if data.get("error"):
        raise RuntimeError(f"Ollama rejected request: {data['error']}")
    message = data.get("message")
    if not isinstance(message, dict):
        raise ValueError("Ollama response has no message")
    parts = []
    if message.get("content"):
        parts.append(types.Part(text=message["content"]))
    for call in message.get("tool_calls") or []:
        function = call["function"]
        arguments = function.get("arguments") or {}
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        if not isinstance(arguments, dict):
            raise ValueError("Ollama tool arguments must be an object")
        parts.append(
            types.Part(
                function_call=types.FunctionCall(
                    name=function["name"],
                    args=arguments,
                )
            )
        )
    if not parts:
        raise ValueError("Ollama returned neither text nor tool calls")
    return LlmResponse(
        content=types.Content(role="model", parts=parts),
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=data.get("prompt_eval_count", 0),
            candidates_token_count=data.get("eval_count", 0),
            total_token_count=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
        ),
    )


class Ollama(BaseLlm):
    base_url: str
    request_timeout: float = 120

    @classmethod
    def supported_models(cls) -> list[str]:
        return []

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        if stream:
            raise ValueError("Ollama adapter supports non-streaming ADK runs only")
        payload = {
            "model": self.model,
            "messages": to_messages(llm_request),
            "tools": to_tools(llm_request),
            "stream": False,
            "options": {"temperature": 0, "num_predict": 2048},
        }
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        async with (
            httpx.AsyncClient(
                timeout=self.request_timeout,
                trust_env=False,
                follow_redirects=False,
                verify=context,
            ) as client,
            client.stream(
                "POST", self.base_url.rstrip("/") + "/api/chat", json=payload
            ) as response,
        ):
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_BYTES:
                    raise ValueError("Ollama response exceeds size limit")
        yield from_response(json.loads(body))
