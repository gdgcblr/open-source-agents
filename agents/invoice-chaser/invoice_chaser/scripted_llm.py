"""A scripted stand-in for Gemini: used by the offline tests and by `cli.py chase --replay`.

Each step is a list of genai Parts, or a callable(llm_request) -> list of Parts.
When the script runs out, the model replies "done".
"""

from typing import Any, AsyncGenerator

from google.adk.models import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import Field


def call(name: str, **args) -> list[types.Part]:
    return [types.Part.from_function_call(name=name, args=args)]


def text(s: str) -> list[types.Part]:
    return [types.Part.from_text(text=s)]


def tool_responses(llm_request: LlmRequest) -> list[dict]:
    """All function responses the model has seen so far, oldest first."""
    out = []
    for content in llm_request.contents:
        for part in content.parts or []:
            if part.function_response:
                out.append({"name": part.function_response.name,
                            "response": part.function_response.response})
    return out


class ScriptedLlm(BaseLlm):
    model: str = "scripted-mock"
    steps: list[Any] = Field(default_factory=list)
    requests: list[Any] = Field(default_factory=list)

    async def generate_content_async(self, llm_request: LlmRequest,
                                     stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
        self.requests.append(llm_request)
        step = self.steps.pop(0) if self.steps else text("done")
        parts = step(llm_request) if callable(step) else step
        yield LlmResponse(content=types.Content(role="model", parts=parts))
