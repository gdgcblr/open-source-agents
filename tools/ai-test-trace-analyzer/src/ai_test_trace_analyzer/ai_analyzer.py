
"""AI analysis of pytest traces using a local Ollama model."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def analyze_test(test: dict[str, Any]) -> dict[str, Any]:
    """Analyze a pytest trace using Ollama's local HTTP API.

    Optional environment variables:
        OLLAMA_HOST: defaults to http://localhost:11434
        OLLAMA_MODEL: defaults to qwen2.5:3b
        OLLAMA_TIMEOUT: request timeout in seconds, defaults to 120
    """

    host = os.getenv(
        "OLLAMA_HOST", "http://localhost:11434"
    ).strip().rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b").strip()

    try:
        timeout = float(os.getenv("OLLAMA_TIMEOUT", "60"))
    except ValueError:
        timeout = 120.0

    if not model:
        return {
            "status": "error",
            "provider": "ollama",
            "error": "OLLAMA_MODEL cannot be empty.",
        }

    nodeid = test.get("nodeid", "Unknown test")
    outcome = test.get("outcome", "unknown")
    failure = test.get("failure")
    events = test.get("events", [])

    # Keep requests manageable for local models.
    prompt_data = {
        "test_name": nodeid,
        "test_outcome": outcome,
        "trace_id": test.get("trace_id"),
        "failure_details": failure,
        "trace_event_count": len(events),
        "recent_trace_events": events[-20:],
    }

    prompt = f"""
You are an experienced Software Development Engineer in Test (SDET).

Analyze this pytest execution trace.

Return ONLY a valid JSON object with these keys:
- summary: concise explanation of what happened
- likely_root_cause: likely cause, or null if the trace is insufficient
- evidence: list of observations supported by the trace
- suggested_checks: list of practical debugging steps
- confidence: one of "high", "medium", or "low"

Rules:
1. Never invent evidence not present in the trace.
2. Distinguish observed facts from hypotheses.
3. For passed tests, explain what the trace shows.
4. For failed tests, investigate the failure and relevant calls.
5. If the failure details contain an HTTP response, inspect nested downstream
   error fields and identify the service that first reported the failure.
6. Use trace_id to correlate events and response details; do not treat an
   upstream 502 as the root cause if a downstream service reports the cause.
7. If evidence is insufficient, say so.
8. Keep the response concise.

Trace data:
{json.dumps(prompt_data, ensure_ascii=False, default=str)}
"""

    url = f"{host}/api/chat"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.2,
        },
    }

    request = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request, timeout=timeout
        ) as response:
            response_data = json.loads(
                response.read().decode("utf-8")
            )

        message = response_data.get("message", {})
        response_text = message.get("content", "").strip()

        if not response_text:
            return {
                "status": "error",
                "provider": "ollama",
                "error": "Ollama returned an empty response.",
            }

        try:
            analysis = json.loads(response_text)
        except json.JSONDecodeError:
            return {
                "status": "error",
                "provider": "ollama",
                "error": "Ollama returned invalid JSON.",
                "raw_response": response_text[:2000],
            }

        if not isinstance(analysis, dict):
            return {
                "status": "error",
                "provider": "ollama",
                "error": "The analysis was not a JSON object.",
            }

        required_keys = {
            "summary",
            "likely_root_cause",
            "evidence",
            "suggested_checks",
            "confidence",
        }

        missing_keys = required_keys - analysis.keys()
        if missing_keys:
            return {
                "status": "error",
                "provider": "ollama",
                "error": "The analysis is missing required fields.",
                "missing_keys": sorted(missing_keys),
                "raw_response": analysis,
            }

        return {
            "status": "success",
            "provider": "ollama",
            "model": response_data.get("model", model),
            "test_name": nodeid,
            "test_outcome": outcome,
            "trace_id": test.get("trace_id"),
            "analysis": analysis,
        }

    except urllib.error.HTTPError as exc:
        try:
            error_body = exc.read().decode(
                "utf-8", errors="replace"
            )
            try:
                error_data = json.loads(error_body)
                message = error_data.get("error", error_body)
            except json.JSONDecodeError:
                message = error_body[:1000]
        except OSError:
            message = "Could not read Ollama's error response."

        return {
            "status": "error",
            "provider": "ollama",
            "http_status": exc.code,
            "error": str(message),
            "hint": (
                "Check that Ollama is running, the model is available, "
                "and the model name is correct."
            ),
        }

    except urllib.error.URLError as exc:
        return {
            "status": "error",
            "provider": "ollama",
            "error": f"Could not connect to Ollama: {exc.reason}",
            "hint": (
                "Start Ollama and verify OLLAMA_HOST. "
                "The default is http://localhost:11434."
            ),
        }

    except TimeoutError:
        return {
            "status": "error",
            "provider": "ollama",
            "error": "The Ollama request timed out.",
            "hint": (
                "Try a smaller trace, increase OLLAMA_TIMEOUT, "
                "or use a smaller local model."
            ),
        }

    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return {
            "status": "error",
            "provider": "ollama",
            "error": f"Could not process Ollama response: {exc}",
        }
