"""Orchestrates policy tools and memory while keeping decisions human-reviewed."""

from __future__ import annotations

import sqlite3
from typing import Any

from .memory import CaseMemory, UnavailableCaseMemory
from .policy import PolicyTool, is_finite_number


class TriageAgent:
    MAX_CASE_ID_LENGTH = 128
    MAX_SUMMARY_LENGTH = 2000
    MAX_FACTS = 64
    MAX_FACT_NAME_LENGTH = 128
    MAX_FACT_STRING_LENGTH = 2000

    def __init__(
        self, policy_tool: PolicyTool, memory: CaseMemory | UnavailableCaseMemory
    ) -> None:
        self.policy_tool = policy_tool
        self.memory = memory

    def triage(self, request: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(request, dict):
            raise ValueError("Request must be a JSON object.")
        required = {"case_id", "summary", "facts"}
        missing = required - request.keys()
        if missing:
            raise ValueError(f"Request is missing fields: {', '.join(sorted(missing))}")
        unexpected = request.keys() - required
        if unexpected:
            raise ValueError(f"Request has unsupported fields: {', '.join(sorted(unexpected))}")
        if not isinstance(request["case_id"], str) or not request["case_id"].strip():
            raise ValueError("'case_id' must be a non-empty string.")
        if len(request["case_id"]) > self.MAX_CASE_ID_LENGTH:
            raise ValueError("'case_id' exceeds the maximum length.")
        if not isinstance(request["summary"], str) or not request["summary"].strip():
            raise ValueError("'summary' must be a non-empty string.")
        if len(request["summary"]) > self.MAX_SUMMARY_LENGTH:
            raise ValueError("'summary' exceeds the maximum length.")
        if not isinstance(request["facts"], dict) or not all(
            isinstance(field, str) and field.strip() for field in request["facts"]
        ):
            raise ValueError("'facts' must be an object with non-empty string field names.")
        if len(request["facts"]) > self.MAX_FACTS:
            raise ValueError("'facts' exceeds the maximum number of fields.")
        supported_fields = {
            condition["field"]
            for rule in self.policy_tool.policy["rules"]
            for condition in rule["when"]
        }
        unsupported_facts = request["facts"].keys() - supported_fields
        if unsupported_facts:
            raise ValueError(
                f"Facts are not used by this policy: {', '.join(sorted(unsupported_facts))}"
            )
        for field, value in request["facts"].items():
            if len(field) > self.MAX_FACT_NAME_LENGTH:
                raise ValueError(f"Fact name {field!r} exceeds the maximum length.")
            if isinstance(value, str):
                if len(value) > self.MAX_FACT_STRING_LENGTH:
                    raise ValueError(f"Fact {field!r} exceeds the maximum string length.")
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                if not is_finite_number(value):
                    raise ValueError(
                        f"Fact {field!r} must be a finite number within signed 64-bit range."
                    )
            elif value is not None and not isinstance(value, bool):
                raise ValueError(f"Fact {field!r} must be a JSON scalar value.")

        retrieved_clauses = self.policy_tool.search(request["summary"])
        rule_result = self.policy_tool.evaluate(request["facts"])
        citations = rule_result["matched_rule_ids"]
        known_rule_ids = {rule["id"] for rule in self.policy_tool.policy["rules"]}
        if not set(citations).issubset(known_rule_ids):
            raise ValueError("Policy evaluation returned an unknown rule citation.")

        result = {
            "case_id": request["case_id"],
            "request_summary": request["summary"],
            "policy_name": self.policy_tool.policy.get("name", ""),
            "policy_version": self.policy_tool.policy.get("version", ""),
            "policy_sha256": self.policy_tool.sha256,
            "recommendation": rule_result["recommendation"],
            "policy_citations": citations,
            "policy_search_results": [clause["id"] for clause in retrieved_clauses],
            "memory_references": [],
            "memory_status": {
                "initialization": (
                    "ok" if getattr(self.memory, "available", True) else "unavailable"
                ),
                "search": "ok" if getattr(self.memory, "available", True) else "skipped",
                "write": "ok" if getattr(self.memory, "available", True) else "skipped",
            },
            "warnings": [],
            "missing_facts": rule_result["missing_facts"],
            "invalid_facts": rule_result["invalid_facts"],
            "rationale": rule_result["reason"],
            "evidence": {
                "provided_facts": request["facts"],
                "policy_text": [
                    rule["rationale"]
                    for rule in self.policy_tool.policy["rules"]
                    if rule["id"] in citations
                ],
            },
            "decision_status": "pending_human_review",
            "needs_human_review": True,
            "action_taken": False,
        }
        if not getattr(self.memory, "available", True):
            result["memory_status"]["initialization_error"] = self.memory.error_type
            result["warnings"].append("case_memory_initialization_unavailable")
            return result
        try:
            prior_cases = self.memory.search(request["summary"])
            result["memory_references"] = [case["case_id"] for case in prior_cases]
        except sqlite3.Error:
            result["memory_status"]["search"] = "unavailable"
            result["warnings"].append("case_memory_search_unavailable")
        try:
            self.memory.remember(result)
        except sqlite3.Error:
            result["memory_status"]["write"] = "unavailable"
            result["warnings"].append("case_memory_write_unavailable")
        return result
