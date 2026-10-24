#!/usr/bin/env python3
"""Small, deterministic-by-default evaluation runner for local Ollama models."""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def normalize_host(host: str) -> str:
    host = host.strip()
    if not host:
        raise ValueError("Ollama host cannot be empty")
    if "://" not in host:
        host = "http://" + host

    parsed = urllib.parse.urlsplit(host)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Host must use http:// or https://")
    if not parsed.hostname:
        raise ValueError(f"Invalid host URL (missing hostname): '{host}'")

    try:
        if parsed.port is not None and not (1 <= parsed.port <= 65535):
            raise ValueError(f"Port must be between 1 and 65535 in '{host}'")
    except ValueError as exc:
        raise ValueError(f"Invalid port in host URL '{host}': {exc}") from None

    netloc = parsed.netloc
    return f"{parsed.scheme}://{netloc}".rstrip("/")


def post_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Do not echo response body: it may contain prompts or other sensitive data.
        raise RuntimeError(f"Ollama returned HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError("Could not connect to Ollama or request timed out") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("Ollama returned invalid JSON") from None

    if not isinstance(data, dict):
        raise RuntimeError("Ollama returned an unexpected response format")
    return data


def load_dataset(path: str | Path) -> list[dict[str, Any]]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Cannot read dataset: {exc}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"Dataset is not valid JSON: {exc}") from None

    if not isinstance(raw, list) or not raw:
        raise ValueError("Dataset must be a non-empty JSON array")

    seen_ids: set[str] = set()
    for index, case in enumerate(raw):
        if not isinstance(case, dict):
            raise ValueError(f"Case {index + 1} must be a JSON object")
        case_id = case.get("id")
        prompt = case.get("prompt")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"Case {index + 1} needs a non-empty string id")
        if case_id in seen_ids:
            raise ValueError(f"Duplicate test id: {case_id}")
        seen_ids.add(case_id)
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"Case '{case_id}' needs a non-empty prompt")

        expected = case.get("expected_substrings", [])
        if not isinstance(expected, list) or not all(isinstance(x, str) for x in expected):
            raise ValueError(f"Case '{case_id}': expected_substrings must be a list of strings")
        if any(not x.strip() for x in expected):
            raise ValueError(f"Case '{case_id}': expected_substrings cannot contain empty or whitespace-only strings")

        has_keys = False
        if "expected_json_keys" in case:
            keys = case["expected_json_keys"]
            if not isinstance(keys, list) or not all(isinstance(x, str) for x in keys):
                raise ValueError(f"Case '{case_id}': expected_json_keys must be a list of strings")
            if not keys:
                raise ValueError(f"Case '{case_id}': expected_json_keys cannot be empty when specified")
            if any(not x.strip() for x in keys):
                raise ValueError(f"Case '{case_id}': expected_json_keys cannot contain empty or whitespace-only keys")
            has_keys = bool(keys)

        for flag in ("expected_json",):
            if flag in case and not isinstance(case[flag], bool):
                raise ValueError(f"Case '{case_id}': {flag} must be true or false")

        has_json = case.get("expected_json", False) is True
        if not expected and not has_json and not has_keys:
            raise ValueError(
                f"Case '{case_id}' defines no assertions. Every case must define at least one: "
                "a non-empty 'expected_substrings', 'expected_json: true', or 'expected_json_keys'."
            )
    return raw


def check_response(case: dict[str, Any], response: str) -> dict[str, Any]:
    """Apply deterministic checks; this is not a semantic-quality judge."""
    failures: list[str] = []
    has_assertions = bool(case.get("expected_substrings")) or (case.get("expected_json") is True) or bool(case.get("expected_json_keys"))
    if not has_assertions:
        failures.append("case defines no assertions")
    normalized = response.casefold()

    missing = [
        expected for expected in case.get("expected_substrings", [])
        if expected.casefold() not in normalized
    ]
    if missing:
        failures.append("missing expected substring(s): " + ", ".join(repr(x) for x in missing))

    parsed_json: Any = None
    json_valid = None
    if case.get("expected_json", False) or "expected_json_keys" in case:
        try:
            parsed_json = json.loads(response)
            json_valid = True
        except json.JSONDecodeError:
            json_valid = False
            failures.append("response is not valid JSON")

    if "expected_json_keys" in case and json_valid:
        if not isinstance(parsed_json, dict):
            failures.append("response JSON is not an object")
        else:
            missing_keys = [key for key in case["expected_json_keys"] if key not in parsed_json]
            if missing_keys:
                failures.append("missing JSON key(s): " + ", ".join(missing_keys))

    return {
        "passed": not failures,
        "failures": failures,
        "checks": {
            "expected_substrings": {
                "expected": case.get("expected_substrings", []),
                "missing": missing,
            },
            "json_valid": json_valid,
        },
    }


def evaluate_case(
    case: dict[str, Any],
    model: str,
    host: str,
    timeout: float,
    temperature: float,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "prompt": case["prompt"],
        "stream": False,
        "options": {"temperature": temperature},
    }
    started = time.perf_counter()
    try:
        response_data = post_json(
            host + "/api/generate", payload=payload, timeout=timeout
        )
        elapsed = time.perf_counter() - started
        output = response_data.get("response")
        if not isinstance(output, str):
            raise RuntimeError("Response did not contain a text field")
        checks = check_response(case, output)
        eval_count = response_data.get("eval_count")
        eval_duration = response_data.get("eval_duration")
        tokens_per_second = None
        if isinstance(eval_count, (int, float)) and isinstance(eval_duration, (int, float)) and eval_duration > 0:
            tokens_per_second = round(eval_count / eval_duration * 1_000_000_000, 2)

        return {
            "id": case["id"],
            "model": model,
            "status": "PASS" if checks["passed"] else "FAIL",
            "latency_seconds": round(elapsed, 3),
            "eval_count": eval_count,
            "prompt_eval_count": response_data.get("prompt_eval_count"),
            "tokens_per_second": tokens_per_second,
            "response": output,
            **checks,
        }
    except RuntimeError as exc:
        return {
            "id": case["id"],
            "model": model,
            "status": "ERROR",
            "latency_seconds": round(time.perf_counter() - started, 3),
            "eval_count": None,
            "prompt_eval_count": None,
            "tokens_per_second": None,
            "response": None,
            "passed": False,
            "failures": [str(exc)],
            "checks": {},
        }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(item["status"] == "PASS" for item in results)
    latencies = [item["latency_seconds"] for item in results]
    speeds = [item["tokens_per_second"] for item in results if item["tokens_per_second"] is not None]
    return {
        "total": total,
        "passed": passed,
        "failed": sum(item["status"] == "FAIL" for item in results),
        "errors": sum(item["status"] == "ERROR" for item in results),
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "mean_latency_seconds": round(statistics.mean(latencies), 3) if latencies else None,
        "median_latency_seconds": round(statistics.median(latencies), 3) if latencies else None,
        "mean_tokens_per_second": round(statistics.mean(speeds), 2) if speeds else None,
    }


def run_evaluation(
    dataset: list[dict[str, Any]],
    models: list[str],
    host: str,
    timeout: float = 120.0,
    temperature: float = 0.0,
) -> dict[str, Any]:
    normalized_host = normalize_host(host)
    results = []
    for model in models:
        for case in dataset:
            results.append(evaluate_case(case, model, normalized_host, timeout, temperature))

    summaries = {
        model: summarize([item for item in results if item["model"] == model])
        for model in models
    }
    return {
        "tool": "agent-eval-lite",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "host": normalized_host,
        "temperature": temperature,
        "dataset_cases": len(dataset),
        "models": models,
        "summary_by_model": summaries,
        "results": results,
        "notes": [
            "Checks are deterministic string/JSON assertions, not semantic grading.",
            "Model outputs are included in the report; review before sharing.",
            "Latency depends on hardware, model loading, and server load.",
        ],
    }


def print_summary(report: dict[str, Any]) -> None:
    print("Agent Eval Lite")
    print("=" * 72)
    print(f"Dataset: {report['dataset_cases']} cases | Models: {', '.join(report['models'])}")
    for model, summary in report["summary_by_model"].items():
        print(
            f"\n{model}: {summary['passed']}/{summary['total']} passed "
            f"({summary['pass_rate']:.0%}) | "
            f"mean latency: {summary['mean_latency_seconds']}s | "
            f"mean generation speed: {summary['mean_tokens_per_second']} tok/s"
        )
    print("-" * 72)
    for result in report["results"]:
        print(f"[{result['status']:<5}] {result['model']} / {result['id']} "
              f"({result['latency_seconds']}s)")
        for failure in result["failures"]:
            print(f"        {failure}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate local Ollama models against a JSON test dataset."
    )
    parser.add_argument("--dataset", default="examples/cases.json", help="Path to JSON dataset")
    parser.add_argument("--models", default="llama3.2", help="Comma-separated Ollama model names")
    parser.add_argument("--host", default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"), help="Ollama base URL (or OLLAMA_HOST)")
    parser.add_argument("--timeout", type=float, default=120.0, help="Per-inference timeout in seconds")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature")
    parser.add_argument("--output", default="eval-report.json", help="Path for JSON report")
    parser.add_argument("--no-save-responses", action="store_true",
                        help="Omit generated response text from the saved report")
    args = parser.parse_args(argv)

    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if not math.isfinite(args.temperature) or args.temperature < 0:
        parser.error("--temperature must be a finite non-negative number")

    models = [item.strip() for item in args.models.split(",") if item.strip()]
    if not models:
        parser.error("--models must contain at least one model")

    try:
        dataset = load_dataset(args.dataset)
        report = run_evaluation(dataset, models, args.host, args.timeout, args.temperature)
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print_summary(report)
    if args.no_save_responses:
        for result in report["results"]:
            result["response"] = None

    try:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"Could not write report: {exc}", file=sys.stderr)
        return 2

    print(f"\nJSON report saved to: {output_path}")
    return 0 if all(item["status"] == "PASS" for item in report["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
