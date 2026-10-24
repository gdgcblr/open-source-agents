"""Deterministic offline evaluations for agent output, tools, and memory."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from .agent import TriageAgent
from .judge import judge_case
from .memory import CaseMemory
from .policy import PolicyTool

MAX_EVALUATION_FIXTURE_BYTES = 2 * 1024 * 1024
MAX_EVALUATION_CASES_PER_GROUP = 100
MAX_LLM_JUDGE_CASES = 20


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key in evaluation fixtures.")
        result[key] = value
    return result


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def run_evaluations(
    fixture_path: Path,
    policy_path: Path,
    use_llm_judge: bool = False,
) -> dict[str, Any]:
    with fixture_path.open("rb") as file:
        raw_fixtures = file.read(MAX_EVALUATION_FIXTURE_BYTES + 1)
    if len(raw_fixtures) > MAX_EVALUATION_FIXTURE_BYTES:
        raise ValueError("Evaluation fixtures exceed the 2 MiB size limit.")
    fixtures = json.loads(
        raw_fixtures.decode("utf-8"),
        object_pairs_hook=_object_without_duplicate_keys,
    )
    if not isinstance(fixtures, dict):
        raise ValueError("Evaluation fixtures must be a JSON object.")
    for group_name in ("agent_cases", "policy_tool_cases", "memory_cases"):
        cases = fixtures.get(group_name)
        if not isinstance(cases, list) or len(cases) > MAX_EVALUATION_CASES_PER_GROUP:
            raise ValueError(
                f"Evaluation fixtures require a {group_name} list of at most 100 cases."
            )
    if use_llm_judge and len(fixtures["agent_cases"]) > MAX_LLM_JUDGE_CASES:
        raise ValueError("LLM judging is limited to 20 agent cases per run.")
    policy = PolicyTool(policy_path)
    with tempfile.TemporaryDirectory(prefix="policy-triage-eval-") as tempdir:
        memory = CaseMemory(Path(tempdir) / "agent-memory.sqlite3")
        agent = TriageAgent(policy, memory)
        agent_cases = []
        judge_failed = False
        try:
            for fixture in fixtures["agent_cases"]:
                output = agent.triage(fixture["request"])
                expected = fixture["expected"]
                valid_schema = all(
                    key in output
                    for key in (
                        "recommendation",
                        "policy_citations",
                        "missing_facts",
                        "invalid_facts",
                        "rationale",
                        "needs_human_review",
                        "action_taken",
                        "decision_status",
                    )
                )
                valid_schema = valid_schema and (
                    output["recommendation"] in {"approve", "deny", "escalate"}
                    and isinstance(output["policy_citations"], list)
                    and all(isinstance(item, str) for item in output["policy_citations"])
                    and isinstance(output["missing_facts"], list)
                    and all(isinstance(item, str) for item in output["missing_facts"])
                    and isinstance(output["invalid_facts"], list)
                    and all(isinstance(item, str) for item in output["invalid_facts"])
                    and isinstance(output["rationale"], str)
                    and bool(output["rationale"].strip())
                    and isinstance(output.get("evidence"), dict)
                    and isinstance(output["evidence"].get("provided_facts"), dict)
                    and isinstance(output["evidence"].get("policy_text"), list)
                    and isinstance(output.get("memory_status"), dict)
                    and isinstance(output.get("warnings"), list)
                    and output["needs_human_review"] is True
                    and output["action_taken"] is False
                    and output["decision_status"] == "pending_human_review"
                )
                rules_by_id = {rule["id"]: rule for rule in policy.policy["rules"]}
                citations = output["policy_citations"]
                faithful_citations = all(
                    citation in rules_by_id
                    and (
                        output["recommendation"] == "escalate"
                        or rules_by_id[citation]["recommendation"]
                        == output["recommendation"]
                    )
                    and policy.rule_matches(
                        rules_by_id[citation], fixture["request"]["facts"]
                    )
                    for citation in citations
                )
                if output["recommendation"] in {"approve", "deny"}:
                    faithful_citations = faithful_citations and bool(citations)
                cited_recommendations = {
                    rules_by_id[citation]["recommendation"]
                    for citation in citations
                    if citation in rules_by_id
                }
                if output["invalid_facts"]:
                    expected_rationale = (
                        "Facts are outside the valid ranges defined by policy."
                    )
                elif output["missing_facts"]:
                    expected_rationale = "Decision-critical facts are missing."
                elif len(cited_recommendations) > 1:
                    expected_rationale = (
                        "Conflicting policy rules apply; human review is required."
                    )
                elif citations:
                    expected_rationale = rules_by_id[citations[0]]["rationale"]
                else:
                    expected_rationale = "No explicit policy rule resolves this request."
                case_eval: dict[str, Any] = {
                    "case_id": fixture["request"]["case_id"],
                    "decision_correct": output["recommendation"]
                    == expected["recommendation"],
                    "complete": valid_schema
                    and bool(output["rationale"])
                    and isinstance(output.get("policy_sha256"), str)
                    and len(output["policy_sha256"]) == 64
                    and "evidence" in output
                    and "provided_facts" in output["evidence"],
                    "faithful_citations": faithful_citations,
                    "rationale_faithfulness": output["rationale"]
                    == expected_rationale,
                    "review_safety": output["needs_human_review"]
                    and output["action_taken"] is False,
                    "output": output,
                }
                if use_llm_judge:
                    if judge_failed:
                        case_eval["llm_judge"] = {
                            "status": "skipped",
                            "reason": "previous_judge_failure",
                        }
                    else:
                        try:
                            case_eval["llm_judge"] = {
                                "status": "ok",
                                "scores": judge_case(
                                    fixture["request"],
                                    {
                                        "expected": expected,
                                        "policy_rules": policy.policy["rules"],
                                    },
                                    output,
                                ),
                            }
                        except (RuntimeError, ValueError) as error:
                            judge_failed = True
                            case_eval["llm_judge"] = {
                                "status": "unavailable",
                                "error_code": getattr(
                                    error, "error_code", type(error).__name__
                                ),
                            }
                agent_cases.append(case_eval)
        finally:
            memory.close()

        policy_tool_cases = []
        for fixture in fixtures["policy_tool_cases"]:
            expected = set(fixture["expected_clause_ids"])
            top_k = fixture.get("top_k", 1)
            retrieved = [
                item["id"] for item in policy.search(fixture["query"], limit=top_k)
            ]
            retrieved_set = set(retrieved)
            first_relevant_rank = next(
                (rank for rank, clause_id in enumerate(retrieved, start=1)
                 if clause_id in expected),
                None,
            )
            policy_tool_cases.append(
                {
                    "query": fixture["query"],
                    "recall_at_k": _rate(len(retrieved_set & expected), len(expected)),
                    "precision_at_k": _rate(len(retrieved_set & expected), len(retrieved)),
                    "reciprocal_rank": (
                        round(1 / first_relevant_rank, 4)
                        if first_relevant_rank is not None
                        else 0.0
                    ),
                    "expected_clause_ids": sorted(expected),
                    "retrieved_clause_ids": retrieved,
                }
            )

        memory = CaseMemory(Path(tempdir) / "memory-eval.sqlite3")
        memory_cases = []
        try:
            for fixture in fixtures["memory_cases"]:
                for record in fixture["records"]:
                    memory.remember(
                        {
                            "case_id": record["case_id"],
                            "request_summary": record["summary"],
                            "recommendation": record["recommendation"],
                            "policy_citations": record["policy_ids"],
                        }
                    )
                retrieved = {
                    item["case_id"]
                    for item in memory.search(
                        fixture["query"], limit=fixture["top_k"]
                    )
                }
                expected = set(fixture["expected_case_ids"])
                memory_cases.append(
                    {
                        "query": fixture["query"],
                        "recall_at_k": _rate(len(retrieved & expected), len(expected)),
                        "expected_case_ids": sorted(expected),
                        "retrieved_case_ids": sorted(retrieved),
                    }
                )
        finally:
            memory.close()

    count = len(agent_cases)
    policy_count = len(policy_tool_cases)
    memory_count = len(memory_cases)
    agent_metrics = {
        "case_count": count,
        "decision_accuracy": _rate(
            sum(case["decision_correct"] for case in agent_cases), count
        ),
        "output_completeness": _rate(
            sum(case["complete"] for case in agent_cases), count
        ),
        "citation_faithfulness": _rate(
            sum(case["faithful_citations"] for case in agent_cases), count
        ),
        "rationale_faithfulness": _rate(
            sum(case["rationale_faithfulness"] for case in agent_cases), count
        ),
        "human_review_safety": _rate(
            sum(case["review_safety"] for case in agent_cases), count
        ),
        "cases": agent_cases,
    }
    policy_tool_metrics = {
        "case_count": policy_count,
        "mean_recall_at_k": _rate(
            sum(case["recall_at_k"] for case in policy_tool_cases), policy_count
        ),
        "mean_precision_at_k": _rate(
            sum(case["precision_at_k"] for case in policy_tool_cases), policy_count
        ),
        "mean_reciprocal_rank": _rate(
            sum(case["reciprocal_rank"] for case in policy_tool_cases), policy_count
        ),
        "cases": policy_tool_cases,
    }
    memory_metrics = {
        "case_count": memory_count,
        "mean_recall_at_k": _rate(
            sum(case["recall_at_k"] for case in memory_cases), memory_count
        ),
        "cases": memory_cases,
    }
    agent_passed = all(
        agent_metrics[metric] == 1.0
        for metric in (
            "decision_accuracy",
            "output_completeness",
            "citation_faithfulness",
            "rationale_faithfulness",
            "human_review_safety",
        )
    )
    policy_tool_passed = all(
        policy_tool_metrics[metric] == 1.0
        for metric in (
            "mean_recall_at_k",
            "mean_precision_at_k",
            "mean_reciprocal_rank",
        )
    )
    memory_passed = memory_metrics["mean_recall_at_k"] == 1.0
    judge_passed = not use_llm_judge or (
        not judge_failed
        and all(
            case.get("llm_judge", {}).get("status") == "ok"
            for case in agent_cases
        )
    )
    return {
        "overall_passed": (
            agent_passed and policy_tool_passed and memory_passed and judge_passed
        ),
        "agent": {
            **agent_metrics,
            "passed": agent_passed,
        },
        "policy_tool": {
            **policy_tool_metrics,
            "passed": policy_tool_passed,
        },
        "memory": {
            **memory_metrics,
            "passed": memory_passed,
        },
        "llm_judge_enabled": use_llm_judge,
        "llm_judge_passed": judge_passed if use_llm_judge else None,
        "llm_judge_failure_code": next(
            (
                case["llm_judge"].get("error_code")
                for case in agent_cases
                if case.get("llm_judge", {}).get("status") == "unavailable"
            ),
            None,
        ),
    }
