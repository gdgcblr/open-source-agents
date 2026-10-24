"""Run local model-backed LifeAdmin evaluations without ADK's eval extras."""

from __future__ import annotations

import argparse
import asyncio
import gc
import json
import os
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from lifeadmin_mcp import storage

DEFAULT_CASES = Path(__file__).resolve().parents[1] / "evals" / "cases.json"


def _next_occurrence(month_day: str, today: date) -> str:
    month, day = (int(part) for part in month_day.split("-"))
    year = today.year
    while True:
        try:
            candidate = date(year, month, day)
        except ValueError:
            year += 1
            continue
        if candidate >= today:
            return candidate.isoformat()
        year += 1


def _resolve_expected(value: Any, today: date) -> Any:
    if isinstance(value, dict):
        if set(value) == {"next_occurrence"}:
            return _next_occurrence(value["next_occurrence"], today)
        if set(value) == {"contains"}:
            return value
        return {key: _resolve_expected(item, today) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_expected(item, today) for item in value]
    return value


def _resolve_setup_reminders(reminders: list[dict[str, Any]], today: date) -> list[dict[str, Any]]:
    resolved = []
    for reminder in reminders:
        item = dict(reminder)
        relative_days = item.pop("days_from_today", None)
        if relative_days is not None:
            item["due_date"] = date.fromordinal(today.toordinal() + relative_days).isoformat()
        resolved.append(item)
    return resolved


def _match_expected(actual: Any, expected: Any, today: date) -> bool:
    expected = _resolve_expected(expected, today)
    if isinstance(expected, dict):
        if set(expected) == {"contains"}:
            return isinstance(actual, str) and expected["contains"].casefold() in actual.casefold()
        if not isinstance(actual, dict):
            return False
        return all(
            key in actual and _match_expected(actual[key], value, today)
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(_match_expected(a, e, today) for a, e in zip(actual, expected))
        )
    return actual == expected


def _tool_sequence_matches(
    actual_calls: list[dict[str, Any]],
    expected_calls: list[dict[str, Any]],
    today: date,
) -> bool:
    return len(actual_calls) == len(expected_calls) and all(
        actual["name"] == expected["name"]
        and _match_expected(actual["args"], expected.get("args", {}), today)
        for actual, expected in zip(actual_calls, expected_calls)
    )


def _response_text(content: Any) -> str:
    if content is None:
        return ""
    return "\n".join(
        part.text
        for part in content.parts or []
        if part.text and not getattr(part, "thought", False)
    )


def _reset_database(database_path: Path, reminders: list[dict[str, Any]]) -> None:
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("DELETE FROM reminders")
        connection.commit()
    finally:
        connection.close()
    for reminder in reminders:
        storage.add_reminder(**reminder)


async def _run_case(
    case: dict[str, Any],
    runner: Any,
    session_service: Any,
    today: date,
) -> dict[str, Any]:
    from google.genai import types

    user_id = f"eval-{case['id']}"
    session = await session_service.create_session(
        app_name="lifeadmin_agent",
        user_id=user_id,
    )
    message = types.Content(
        role="user",
        parts=[types.Part(text=case["prompt"])],
    )
    tool_calls: list[dict[str, Any]] = []
    final_response = ""

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=message,
    ):
        for call in event.get_function_calls():
            tool_calls.append({"name": call.name, "args": call.args or {}})
        if event.is_final_response():
            final_response = _response_text(event.content)

    expected_sequences = case.get(
        "expected_tool_sequences",
        [case.get("expected_tool_calls", [])],
    )
    calls_match = any(
        _tool_sequence_matches(tool_calls, sequence, today)
        for sequence in expected_sequences
    )
    response_match = all(
        phrase.casefold() in final_response.casefold()
        for phrase in case.get("response_contains", [])
    ) and all(
        any(phrase.casefold() in final_response.casefold() for phrase in alternatives)
        for alternatives in case.get("response_contains_any", [])
    )
    reminders = storage.list_reminders(status="all")
    state_match = all(
        any(_match_expected(reminder, expected, today) for reminder in reminders)
        for expected in case.get("expected_reminders", [])
    ) and len(reminders) == case.get("expected_reminder_count", len(reminders))

    return {
        "id": case["id"],
        "passed": calls_match and response_match and state_match,
        "tool_calls_match": calls_match,
        "response_match": response_match,
        "state_match": state_match,
        "tool_calls": tool_calls,
        "response": final_response,
    }


async def _run_evaluations(
    cases: list[dict[str, Any]],
    database_path: Path,
) -> list[dict[str, Any]]:
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    os.environ["LIFEADMIN_DB_PATH"] = str(database_path)
    storage.list_reminders(status="all")

    from lifeadmin_agent.agent import create_agent

    session_service = InMemorySessionService()
    runner = Runner(
        agent=create_agent(),
        app_name="lifeadmin_agent",
        session_service=session_service,
    )
    results = []
    today = date.today()
    try:
        for case in cases:
            setup_reminders = _resolve_setup_reminders(case.get("setup_reminders", []), today)
            _reset_database(database_path, setup_reminders)
            result = await _run_case(case, runner, session_service, today)
            results.append(result)
            status = "PASS" if result["passed"] else "FAIL"
            print(f"{status} {result['id']}")
            if not result["passed"]:
                expected_sequences = case.get(
                    "expected_tool_sequences",
                    [case.get("expected_tool_calls", [])],
                )
                print(
                    "  score: "
                    f"tools={result['tool_calls_match']} "
                    f"response={result['response_match']} "
                    f"state={result['state_match']}"
                )
                print(f"  expected tools: {expected_sequences}")
                print(f"  actual tools:   {result['tool_calls']}")
                print(f"  response:       {result['response']}")
                if not result["state_match"]:
                    print(f"  reminder state: {storage.list_reminders(status='all')}")
    finally:
        await runner.close()
        await asyncio.sleep(0.2)
        gc.collect()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--model", default=os.getenv("LIFEADMIN_MODEL", "gemma4:e4b"))
    parser.add_argument(
        "--ollama-api-base",
        default=os.getenv("OLLAMA_API_BASE", "http://localhost:11434"),
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="case_ids",
        help="Run only this case ID; repeat the option to select multiple cases.",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON evaluation report path.")
    args = parser.parse_args()

    try:
        dataset = json.loads(args.cases.read_text(encoding="utf-8"))
        cases = dataset["cases"]
        if not cases:
            raise ValueError("the eval dataset must contain at least one case")
        if len({case["id"] for case in cases}) != len(cases):
            raise ValueError("eval case IDs must be unique")
        if args.case_ids:
            unknown_ids = set(args.case_ids) - {case["id"] for case in cases}
            if unknown_ids:
                raise ValueError(f"unknown eval case IDs: {', '.join(sorted(unknown_ids))}")
            cases = [case for case in cases if case["id"] in set(args.case_ids)]
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        parser.error(f"invalid eval dataset: {error}")

    os.environ["LIFEADMIN_MODEL"] = args.model
    os.environ["OLLAMA_API_BASE"] = args.ollama_api_base
    with TemporaryDirectory(prefix="lifeadmin-eval-") as temp_dir:
        database_path = Path(temp_dir) / "eval.sqlite3"
        results = asyncio.run(_run_evaluations(cases, database_path))

    passed = sum(result["passed"] for result in results)
    print(f"\nResult: {passed}/{len(results)} cases passed")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                {
                    "model": args.model,
                    "ollama_api_base": args.ollama_api_base,
                    "passed": passed,
                    "total": len(results),
                    "cases": results,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Report: {args.output}")
    if passed != len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
