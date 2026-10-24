"""Policy loading, retrieval, and deterministic rule evaluation."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

MAX_POLICY_BYTES = 1024 * 1024
MAX_POLICY_ITEMS = 500
MAX_RULE_CONDITIONS = 32
MAX_POLICY_VALUE_LENGTH = 2000


def is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, int):
        return -(2**63) <= value <= 2**63 - 1
    return math.isfinite(value)


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key in policy.")
        result[key] = value
    return result


class PolicyTool:
    """Searches policy clauses and evaluates explicit, structured rules."""

    def __init__(self, policy_path: Path) -> None:
        with policy_path.open("rb") as file:
            raw_policy = file.read(MAX_POLICY_BYTES + 1)
        if len(raw_policy) > MAX_POLICY_BYTES:
            raise ValueError("Policy JSON exceeds the 1 MiB size limit.")
        self.sha256 = hashlib.sha256(raw_policy).hexdigest()
        self.policy: dict[str, Any] = json.loads(
            raw_policy.decode("utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
        )
        if not isinstance(self.policy, dict):
            raise ValueError("Policy must be a JSON object.")
        for metadata_field in ("name", "version"):
            metadata_value = self.policy.get(metadata_field, "")
            if not isinstance(metadata_value, str) or len(metadata_value) > 128:
                raise ValueError(
                    f"Policy {metadata_field} must be a string of at most 128 characters."
                )
        if not isinstance(self.policy.get("rules"), list) or not isinstance(
            self.policy.get("clauses"), list
        ):
            raise ValueError("Policy must contain 'rules' and 'clauses' lists.")
        if not isinstance(self.policy.get("fact_constraints", {}), dict):
            raise ValueError("Policy 'fact_constraints' must be an object.")
        if not self.policy["rules"] or not self.policy["clauses"]:
            raise ValueError("Policy must contain at least one rule and one clause.")
        if (
            len(self.policy["rules"]) > MAX_POLICY_ITEMS
            or len(self.policy["clauses"]) > MAX_POLICY_ITEMS
        ):
            raise ValueError("Policy cannot contain more than 500 rules or clauses.")
        if not all(isinstance(rule, dict) for rule in self.policy["rules"]):
            raise ValueError("Each policy rule must be an object.")
        if not all(isinstance(clause, dict) for clause in self.policy["clauses"]):
            raise ValueError("Each policy clause must be an object.")
        self._validate_policy()

    def _validate_policy(self) -> None:
        rule_ids = [rule.get("id") for rule in self.policy["rules"]]
        clause_ids = [clause.get("id") for clause in self.policy["clauses"]]
        if (
            any(
                not isinstance(identifier, str)
                or not identifier.strip()
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", identifier)
                for identifier in rule_ids
            )
            or len(set(rule_ids)) != len(rule_ids)
        ):
            raise ValueError("Policy rule IDs must be unique, non-empty strings.")
        if (
            any(
                not isinstance(identifier, str)
                or not identifier.strip()
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", identifier)
                for identifier in clause_ids
            )
            or len(set(clause_ids)) != len(clause_ids)
        ):
            raise ValueError("Policy clause IDs must be unique, non-empty strings.")
        for rule in self.policy["rules"]:
            if (
                not isinstance(rule.get("recommendation"), str)
                or rule["recommendation"] not in {"approve", "deny", "escalate"}
                or not isinstance(rule.get("rationale"), str)
                or not rule["rationale"].strip()
                or len(rule["rationale"]) > MAX_POLICY_VALUE_LENGTH
                or not isinstance(rule.get("when"), list)
                or not rule["when"]
                or len(rule["when"]) > MAX_RULE_CONDITIONS
            ):
                raise ValueError(f"Policy rule {rule['id']!r} has invalid fields.")
            for condition in rule["when"]:
                if (
                    not isinstance(condition, dict)
                    or not isinstance(condition.get("field"), str)
                    or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", condition["field"])
                    or not isinstance(condition.get("operator"), str)
                    or condition["operator"] not in {"eq", "lte", "gte", "lt", "gt", "in"}
                    or "value" not in condition
                ):
                    raise ValueError(f"Policy rule {rule['id']!r} has an invalid condition.")
                if condition["operator"] == "in" and not isinstance(
                    condition["value"], list
                ):
                    raise ValueError(
                        f"Policy rule {rule['id']!r} requires a list for 'in'."
                    )
                if condition["operator"] == "in" and (
                    not condition["value"]
                    or len(condition["value"]) > 100
                    or not all(
                        item is None
                        or (
                            isinstance(item, (str, int, float, bool))
                            and (
                                not isinstance(item, str)
                                or len(item) <= MAX_POLICY_VALUE_LENGTH
                            )
                            and (
                                not isinstance(item, (int, float))
                                or is_finite_number(item)
                            )
                        )
                        for item in condition["value"]
                    )
                ):
                    raise ValueError(
                        f"Policy rule {rule['id']!r} requires scalar values for 'in'."
                    )
                if condition["operator"] == "eq" and not (
                    condition["value"] is None
                    or (
                        isinstance(condition["value"], (str, int, float, bool))
                        and (
                            not isinstance(condition["value"], str)
                            or len(condition["value"]) <= MAX_POLICY_VALUE_LENGTH
                        )
                        and (
                            not isinstance(condition["value"], (int, float))
                            or is_finite_number(condition["value"])
                        )
                    )
                ):
                    raise ValueError(
                        f"Policy rule {rule['id']!r} requires a scalar value for 'eq'."
                    )
                if condition["operator"] in {"lte", "gte", "lt", "gt"} and (
                    not is_finite_number(condition["value"])
                ):
                    raise ValueError(
                        f"Policy rule {rule['id']!r} requires a number for "
                        f"{condition['operator']!r}."
                    )
        for clause in self.policy["clauses"]:
            if (
                not isinstance(clause.get("text"), str)
                or not clause["text"].strip()
                or len(clause["text"]) > MAX_POLICY_VALUE_LENGTH
                or not isinstance(clause.get("tags", []), list)
                or len(clause.get("tags", [])) > 100
                or not all(isinstance(tag, str) for tag in clause.get("tags", []))
                or any(len(tag) > 128 for tag in clause.get("tags", []))
            ):
                raise ValueError(f"Policy clause {clause['id']!r} has invalid fields.")
        rule_fields = {
            condition["field"]
            for rule in self.policy["rules"]
            for condition in rule["when"]
        }
        for field, constraint in self.policy.get("fact_constraints", {}).items():
            if (
                not isinstance(field, str)
                or field not in rule_fields
                or not isinstance(constraint, dict)
                or set(constraint) - {"minimum", "maximum", "integer"}
            ):
                raise ValueError(f"Policy has invalid constraints for fact {field!r}.")
            if "integer" in constraint and not isinstance(constraint["integer"], bool):
                raise ValueError(f"Fact {field!r} integer constraint must be boolean.")
            for bound in ("minimum", "maximum"):
                if bound in constraint and not is_finite_number(constraint[bound]):
                    raise ValueError(f"Fact {field!r} {bound} must be a finite number.")
            if (
                "minimum" in constraint
                and "maximum" in constraint
                and constraint["minimum"] > constraint["maximum"]
            ):
                raise ValueError(f"Fact {field!r} has an inverted numeric range.")

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        if not isinstance(query, str) or len(query) > 2000:
            raise ValueError("Policy search query must be a string of at most 2000 chars.")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
            raise ValueError("Policy search limit must be an integer from 1 to 20.")
        query_tokens = tokens(query)
        scored: list[tuple[int, int, dict[str, Any]]] = []
        for index, clause in enumerate(self.policy["clauses"]):
            searchable = " ".join(
                [clause["id"], clause["text"], *clause.get("tags", [])]
            )
            score = len(query_tokens & tokens(searchable))
            if score:
                scored.append((score, -index, clause))
        scored.sort(reverse=True, key=lambda row: (row[0], row[1]))
        return [clause for _, _, clause in scored[:limit]]

    def evaluate(self, facts: dict[str, Any]) -> dict[str, Any]:
        invalid_facts = []
        for field, constraint in self.policy.get("fact_constraints", {}).items():
            value = facts.get(field)
            if value is None:
                continue
            if not is_finite_number(value):
                invalid_facts.append(field)
                continue
            if constraint.get("integer", False) and not isinstance(value, int):
                invalid_facts.append(field)
                continue
            if "minimum" in constraint and value < constraint["minimum"]:
                invalid_facts.append(field)
                continue
            if "maximum" in constraint and value > constraint["maximum"]:
                invalid_facts.append(field)
        if invalid_facts:
            return {
                "recommendation": "escalate",
                "matched_rule_ids": [],
                "missing_facts": [],
                "invalid_facts": sorted(set(invalid_facts)),
                "reason": "Facts are outside the valid ranges defined by policy.",
            }

        matches = []
        possible_matches = []
        for rule in self.policy["rules"]:
            missing = []
            contradicts_rule = False
            for condition in rule["when"]:
                field = condition["field"]
                if facts.get(field) is None:
                    missing.append(field)
                elif not self._condition_matches(facts[field], condition):
                    contradicts_rule = True
                    break
            if contradicts_rule:
                continue
            if missing:
                possible_matches.append((rule, missing))
            else:
                matches.append(rule)

        recommendations = {rule["recommendation"] for rule in matches}
        possible_recommendations = {
            rule["recommendation"] for rule, _ in possible_matches
        }
        unresolved_fields = sorted(
            {field for _, missing in possible_matches for field in missing}
        )
        combined_recommendations = recommendations | possible_recommendations

        if possible_matches and not matches:
            return {
                "recommendation": "escalate",
                "matched_rule_ids": [],
                "missing_facts": unresolved_fields,
                "invalid_facts": [],
                "reason": "Decision-critical facts are missing.",
            }
        if len(combined_recommendations) > 1:
            return {
                "recommendation": "escalate",
                "matched_rule_ids": [rule["id"] for rule in matches],
                "missing_facts": unresolved_fields,
                "invalid_facts": [],
                "reason": "Conflicting policy rules apply; human review is required.",
            }
        if len(recommendations) == 1:
            rule = matches[0]
            return {
                "recommendation": rule["recommendation"],
                "matched_rule_ids": [item["id"] for item in matches],
                "missing_facts": [],
                "invalid_facts": [],
                "reason": rule["rationale"],
            }
        if len(recommendations) > 1:
            reason = "Conflicting policy rules apply; human review is required."
        else:
            reason = "No explicit policy rule resolves this request."
        return {
            "recommendation": "escalate",
            "matched_rule_ids": [rule["id"] for rule in matches],
            "missing_facts": [],
            "invalid_facts": [],
            "reason": reason,
        }

    @classmethod
    def rule_matches(cls, rule: dict[str, Any], facts: dict[str, Any]) -> bool:
        return all(
            cls._condition_matches(facts.get(condition["field"]), condition)
            for condition in rule["when"]
        )

    @staticmethod
    def _condition_matches(actual: Any, condition: dict[str, Any]) -> bool:
        expected = condition["value"]
        operator = condition["operator"]
        if operator == "eq":
            if isinstance(actual, bool) != isinstance(expected, bool):
                return False
            return actual == expected
        if operator == "lte":
            return is_finite_number(actual) and actual <= expected
        if operator == "gte":
            return is_finite_number(actual) and actual >= expected
        if operator == "lt":
            return is_finite_number(actual) and actual < expected
        if operator == "gt":
            return is_finite_number(actual) and actual > expected
        if operator == "in":
            return any(
                isinstance(actual, bool) == isinstance(item, bool) and actual == item
                for item in expected
            )
        raise ValueError(f"Unsupported policy operator: {operator}")
