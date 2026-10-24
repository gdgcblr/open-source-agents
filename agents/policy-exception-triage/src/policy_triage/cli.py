"""Command-line interface for policy triage and evaluations."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .agent import TriageAgent
from .evaluation import run_evaluations
from .memory import open_case_memory
from .pilot import evaluate_reviewed_pilot, prepare_review_dataset
from .policy import PolicyTool

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "data" / "sample_policy.json"
DEFAULT_FIXTURES = ROOT / "evals" / "fixtures.json"
DEFAULT_DATABASE = Path(os.environ.get("POLICY_TRIAGE_DB", ":memory:"))
MAX_REQUEST_BYTES = 64 * 1024


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key.")
        result[key] = value
    return result


def _read_json(path: str | None) -> dict[str, Any]:
    if path:
        with Path(path).open("rb") as file:
            value = file.read(MAX_REQUEST_BYTES + 1)
    else:
        value = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    return _parse_request_json(value)


def _parse_request_json(value: bytes) -> dict[str, Any]:
    if not value.strip():
        raise ValueError("Pass a request JSON file or pipe JSON to stdin.")
    if len(value) > MAX_REQUEST_BYTES:
        raise ValueError("Request JSON exceeds the 64 KiB size limit.")
    parsed = json.loads(
        value.decode("utf-8"), object_pairs_hook=_object_without_duplicate_keys
    )
    if not isinstance(parsed, dict):
        raise ValueError("Request JSON must be an object.")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(prog="policy-triage")
    commands = parser.add_subparsers(dest="command", required=True)

    triage_parser = commands.add_parser("triage", help="Triage one exception request.")
    triage_parser.add_argument("--request", help="Path to request JSON (default: stdin).")
    triage_parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    triage_parser.add_argument("--db", type=Path, default=DEFAULT_DATABASE)

    forget_parser = commands.add_parser("forget", help="Delete locally stored case memory.")
    forget_parser.add_argument("--db", type=Path, required=True)
    forget_group = forget_parser.add_mutually_exclusive_group(required=True)
    forget_group.add_argument("--case-id", help="Delete one case by its ID.")
    forget_group.add_argument("--all", action="store_true", help="Delete every stored case.")
    forget_parser.add_argument(
        "--confirm", action="store_true", help="Required together with --all."
    )

    prepare_parser = commands.add_parser(
        "prepare-pilot", help="Create a review worksheet from synthetic candidates."
    )
    prepare_parser.add_argument("--candidates", type=Path, required=True)
    prepare_parser.add_argument("--output", type=Path, required=True)
    prepare_parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)

    eval_parser = commands.add_parser("eval", help="Run agent, tool, and memory evals.")
    eval_parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    eval_parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    eval_parser.add_argument(
        "--reviewed-cases",
        type=Path,
        help="Policy-owner-reviewed pilot dataset; no data is sent externally.",
    )
    eval_parser.add_argument(
        "--summary",
        action="store_true",
        help="Print aggregate evaluation metrics instead of every case.",
    )
    eval_parser.add_argument(
        "--llm-judge",
        action="store_true",
        help="Request optional LLM-as-judge scores (requires external-call consent).",
    )
    eval_parser.add_argument(
        "--allow-external-llm",
        action="store_true",
        help="Explicitly permit sending redacted evaluation data to api.openai.com.",
    )
    args = parser.parse_args()

    try:
        if args.command == "triage":
            policy = PolicyTool(args.policy)
            memory = open_case_memory(args.db)
            try:
                output = TriageAgent(policy, memory).triage(_read_json(args.request))
            finally:
                memory.close()
        elif args.command == "forget":
            if args.all and not args.confirm:
                raise ValueError("--all requires --confirm.")
            memory = open_case_memory(args.db)
            try:
                if not memory.available:
                    raise RuntimeError(
                        f"Case memory is unavailable ({memory.error_type}); no records were deleted."
                    )
                output = {
                    "deleted_cases": memory.forget(args.case_id, args.all)
                }
            finally:
                memory.close()
        elif args.command == "prepare-pilot":
            output = {
                "prepared_candidates": prepare_review_dataset(
                    args.candidates, args.output, args.policy
                ),
                "output": str(args.output),
                "status": "candidate_not_reviewed",
            }
        else:
            if args.llm_judge and not args.allow_external_llm:
                raise ValueError(
                    "--llm-judge requires --allow-external-llm because evaluation "
                    "data is sent to an external service."
                )
            if args.allow_external_llm and not args.llm_judge:
                raise ValueError("--allow-external-llm must be used with --llm-judge.")
            output = run_evaluations(args.fixtures, args.policy, args.llm_judge)
            output["pilot"] = (
                evaluate_reviewed_pilot(args.reviewed_cases, args.policy)
                if args.reviewed_cases
                else {
                    "status": "not_configured",
                    "message": "Supply --reviewed-cases to measure pilot outcomes.",
                }
            )
            if args.summary:
                output = {
                    "overall_passed": output["overall_passed"],
                    "agent": {
                        key: output["agent"][key]
                        for key in (
                            "case_count",
                            "decision_accuracy",
                            "output_completeness",
                            "citation_faithfulness",
                            "rationale_faithfulness",
                            "human_review_safety",
                            "passed",
                        )
                    },
                    "policy_tool": {
                        key: output["policy_tool"][key]
                        for key in (
                            "case_count",
                            "mean_recall_at_k",
                            "mean_precision_at_k",
                            "mean_reciprocal_rank",
                            "passed",
                        )
                    },
                    "memory": {
                        key: output["memory"][key]
                        for key in ("case_count", "mean_recall_at_k", "passed")
                    },
                    "llm_judge_enabled": output["llm_judge_enabled"],
                    "llm_judge_passed": output["llm_judge_passed"],
                    "llm_judge_failure_code": output["llm_judge_failure_code"],
                    "pilot": (
                        {
                            key: value
                            for key, value in output["pilot"].items()
                            if key != "cases"
                        }
                        if output["pilot"]["status"] == "measured"
                        else output["pilot"]
                    ),
                }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        if args.command == "eval" and not output["overall_passed"]:
            raise SystemExit(1)
    except (OSError, ValueError, RuntimeError, KeyError, sqlite3.Error) as error:
        parser.exit(2, f"Error: {error}\n")


if __name__ == "__main__":
    main()
