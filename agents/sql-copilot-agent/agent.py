"""The SQL Copilot agent, built on the Google Agent Development Kit (ADK).

The agent is given two tools (``inspect_schema`` and ``run_query``) and ADK
runs the tool-use loop:

    plan -> call a tool -> observe the result -> (self-correct) -> answer

The important part is the self-correction: when ``run_query`` returns a SQL
error or an empty result, ADK feeds that back to the model, which rewrites the
query and tries again. That loop is what makes this an agent rather than a
one-shot text-to-SQL prompt. We stream ADK's events to print each step so the
reasoning is visible live.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any

from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner
from google.genai import errors as genai_errors
from google.genai import types

from database import execute_transaction, inspect_schema, run_query

APP_NAME = "sql_copilot"
USER_ID = "local-user"
DEFAULT_MODEL = os.getenv("MODEL_NAME", "gemini-3.8-flash")

SYSTEM_PROMPT = """You are SQL Copilot, an expert data assistant for a SQLite \
e-commerce database. You can both ANSWER questions (read) and MAKE CHANGES \
(create/update records) from plain-English instructions — the user never \
fills in a form; you translate their words into SQL.

Rules:
1. ALWAYS call `inspect_schema` first to learn the exact tables, columns, and \
the SQL dialect in use (shown on the first line). Never guess column names.
2. To ANSWER a question, call `run_query` with a single read-only SELECT (or \
WITH ... SELECT) statement.
3. If a tool returns ok=false, read the error carefully, fix your SQL, and try \
again. Do not give up after one failed attempt.
4. Write SQL for the reported dialect. Treat date columns as ISO strings \
(YYYY-MM-DD) unless the schema shows a native date/timestamp type.

Making changes (writes):
5. To CREATE or UPDATE records, FIRST use `run_query` to resolve the real ids \
you need (e.g. the customer_id for a name, the product_id and price for a \
product). Never invent ids.
6. Then call `execute_transaction` with a list of INSERT/UPDATE statements \
that must all succeed together, plus a short `summary` of the change. When an \
INSERT auto-assigns an id you need for a follow-up statement in the same \
transaction, use the dialect's function for the last inserted id — \
`last_insert_rowid()` on SQLite, `lastval()` on PostgreSQL, \
`LAST_INSERT_ID()` on MySQL.
7. GUARDRAILS you must respect:
   - NEVER hard-delete. To remove/deactivate a record, soft-delete it with \
`UPDATE <table> SET is_deleted = 1 WHERE ...`. DELETE is blocked.
   - NEVER attempt DROP, ALTER, CREATE, TRUNCATE or any schema change. They \
are blocked.
   - When reading "active" records, filter `WHERE is_deleted = 0`.
   The user will be asked to confirm before any write is committed.
8. When done, reply in plain English with the key result. On a final line, \
show the SQL you used, prefixed with `SQL:`.

Be concise. Prefer one good query over many."""


def _ensure_api_key() -> None:
    """Validate that a key is available.

    The underlying Google GenAI SDK reads either ``GOOGLE_API_KEY`` or
    ``GEMINI_API_KEY`` on its own, so we only check that one is present and do
    not copy it (copying would leave both set and trigger a noisy SDK notice).
    """
    if not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")):
        raise RuntimeError(
            "No API key found. Set GEMINI_API_KEY in your environment or .env "
            "file (get one free at https://aistudio.google.com/apikey)."
        )
    # Use the Gemini Developer API (AI Studio key), not Vertex AI.
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "0")


def build_agent(model: str = DEFAULT_MODEL) -> Agent:
    """Construct the ADK agent with its two tools.

    ADK inspects each function's type hints and docstring to build the tool
    declaration automatically, so ``inspect_schema`` and ``run_query`` are
    passed as plain callables.
    """
    return Agent(
        name="sql_copilot",
        model=model,
        description="Answers natural-language questions over a SQLite database.",
        instruction=SYSTEM_PROMPT,
        tools=[inspect_schema, run_query, execute_transaction],
        generate_content_config=types.GenerateContentConfig(temperature=0),
    )


@dataclass
class AgentResult:
    """Outcome of one agent run, including the tool trace for transparency."""

    answer: str
    steps: int
    trace: list[str] = field(default_factory=list)


class SqlCopilotAgent:
    """Natural-language-to-answer agent over the demo SQLite database."""

    def __init__(self, model: str = DEFAULT_MODEL, verbose: bool = True):
        _ensure_api_key()
        self.agent = build_agent(model)
        self.runner = InMemoryRunner(agent=self.agent, app_name=APP_NAME)
        self.verbose = verbose

    def _log(self, message: str, trace: list[str]) -> None:
        trace.append(message)
        if self.verbose:
            print(message)

    def ask(self, question: str) -> AgentResult:
        """Run the agent loop for a single natural-language question.

        Transient API errors (e.g. a 503 when the model is busy) are caught and
        returned as a friendly message instead of a traceback, so the REPL and
        demos keep running.
        """
        try:
            return asyncio.run(self._ask_async(question))
        except genai_errors.APIError as exc:
            code = getattr(exc, "code", "?")
            hint = ""
            if str(code) == "503":
                hint = " The model is temporarily busy — please try again."
            elif str(code) == "429":
                hint = " Rate limit hit — wait a moment and retry."
            return AgentResult(
                answer=f"(API error {code}: {getattr(exc, 'message', exc)}.{hint})",
                steps=0,
            )

    async def _ask_async(self, question: str) -> AgentResult:
        session = await self.runner.session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID
        )
        message = types.Content(role="user", parts=[types.Part(text=question)])

        trace: list[str] = []
        steps = 0
        answer = ""

        async for event in self.runner.run_async(
            user_id=USER_ID, session_id=session.id, new_message=message
        ):
            parts = (
                event.content.parts
                if event.content and event.content.parts
                else []
            )
            for part in parts:
                if getattr(part, "function_call", None):
                    steps += 1
                    call = part.function_call
                    args = dict(call.args) if call.args else {}
                    self._log(f"  step {steps}: → {call.name}({_fmt_args(args)})", trace)
                elif getattr(part, "function_response", None):
                    value = _response_value(part.function_response)
                    self._log(f"  step {steps}: ← {_fmt_result(value)}", trace)

            if event.is_final_response() and parts:
                answer = "".join(
                    p.text for p in parts if getattr(p, "text", None)
                ).strip()

        return AgentResult(
            answer=answer or "(no answer produced)", steps=steps, trace=trace
        )


# --------------------------------------------------------------------------- #
# Small formatting helpers
# --------------------------------------------------------------------------- #
def _response_value(function_response: Any) -> Any:
    """Unwrap ADK's function-response envelope back to the tool's return value."""
    response = getattr(function_response, "response", None)
    if isinstance(response, dict) and set(response.keys()) == {"result"}:
        return response["result"]
    return response


def _fmt_args(args: dict[str, Any]) -> str:
    if "sql" in args:
        return f"sql={args['sql']!r}"
    if "statements" in args:
        statements = args.get("statements") or []
        summary = args.get("summary") or ""
        label = f'"{summary}" — ' if summary else ""
        return f"{label}{len(statements)} statement(s): {statements}"
    return ", ".join(f"{k}={v!r}" for k, v in args.items())


def _fmt_result(result: Any) -> str:
    if isinstance(result, dict):
        if result.get("cancelled"):
            return "cancelled by user"
        if result.get("rolled_back"):
            return f"ROLLED BACK — {result.get('error')}"
        if result.get("ok") is False:
            return f"error: {result.get('error')}"
        if result.get("committed"):
            return (
                f"committed, {result.get('rows_affected', 0)} row(s) affected"
            )
        if "row_count" in result:
            return f"ok, {result['row_count']} row(s)"
    if isinstance(result, str):
        return f"schema ({len(result)} chars)"
    return "ok"
