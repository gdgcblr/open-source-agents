"""Metrics for policy-owner-reviewed, human-reviewed pilot cases."""

from __future__ import annotations

import json
import math
import os
import statistics
import tempfile
from pathlib import Path
from typing import Any

from .agent import TriageAgent
from .memory import CaseMemory
from .policy import PolicyTool

DECISIONS = {"approve", "deny", "escalate"}
MAX_PILOT_FILE_BYTES = 2 * 1024 * 1024
MAX_PILOT_CASES = 1000


def _read_reviewed_cases(path: Path, policy_sha256: str) -> list[dict[str, Any]]:
    with path.open("rb") as file:
        contents = file.read(MAX_PILOT_FILE_BYTES + 1)
    if len(contents) > MAX_PILOT_FILE_BYTES:
        raise ValueError("Reviewed pilot cases exceed the 2 MiB size limit.")
    document = json.loads(contents.decode("utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("cases"), list):
        raise ValueError("Reviewed pilot data must contain a 'cases' list.")
    cases = document["cases"]
    if not cases or len(cases) > MAX_PILOT_CASES:
        raise ValueError("Reviewed pilot data must contain 1 to 1000 cases.")
    seen_ids = set()
    for record in cases:
        if not isinstance(record, dict):
            raise ValueError("Each reviewed pilot case must be an object.")
        case_id = record.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in seen_ids:
            raise ValueError("Reviewed case IDs must be unique non-empty strings.")
        seen_ids.add(case_id)
        if record.get("review_status") != "reviewed":
            raise ValueError(f"Case {case_id!r} is not marked reviewed.")
        if record.get("candidate_only") is not False:
            raise ValueError(
                f"Case {case_id!r} is still a synthetic review candidate."
            )
        if not isinstance(record.get("reviewer_id"), str) or not record["reviewer_id"]:
            raise ValueError(f"Case {case_id!r} needs a pseudonymous reviewer_id.")
        if record.get("policy_sha256") != policy_sha256:
            raise ValueError(
                f"Case {case_id!r} was not reviewed against the loaded policy fingerprint."
            )
        request = record.get("request")
        if not isinstance(request, dict) or request.get("case_id") != case_id:
            raise ValueError(f"Case {case_id!r} has an invalid request.")
        if record.get("human_decision") not in DECISIONS:
            raise ValueError(f"Case {case_id!r} has an invalid human_decision.")
        if not isinstance(record.get("expected_citations"), list) or not all(
            isinstance(item, str) for item in record["expected_citations"]
        ):
            raise ValueError(f"Case {case_id!r} needs expected_citations.")
        if not isinstance(record.get("expected_facts"), dict):
            raise ValueError(f"Case {case_id!r} needs expected_facts.")
        for field in ("baseline_seconds", "assisted_seconds"):
            value = record.get(field)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError(f"Case {case_id!r} has invalid {field}.")
    return cases


def prepare_review_dataset(
    candidates_path: Path, output_path: Path, policy_path: Path
) -> int:
    with candidates_path.open("rb") as file:
        contents = file.read(MAX_PILOT_FILE_BYTES + 1)
    if len(contents) > MAX_PILOT_FILE_BYTES:
        raise ValueError("Pilot candidates exceed the 2 MiB size limit.")
    document = json.loads(contents.decode("utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("cases"), list):
        raise ValueError("Pilot candidates must contain a 'cases' list.")
    candidates = document["cases"]
    if not candidates or len(candidates) > MAX_PILOT_CASES:
        raise ValueError("Pilot candidates must contain 1 to 1000 cases.")

    policy = PolicyTool(policy_path)
    review_cases = []
    seen_ids = set()
    for candidate in candidates:
        if not isinstance(candidate, dict) or candidate.get("candidate_only") is not True:
            raise ValueError("Only explicitly marked synthetic review candidates are accepted.")
        case_id = candidate.get("case_id")
        request = candidate.get("request")
        if (
            not isinstance(case_id, str)
            or not case_id
            or case_id in seen_ids
            or not isinstance(request, dict)
            or request.get("case_id") != case_id
            or not isinstance(candidate.get("candidate_decision"), str)
            or candidate["candidate_decision"] not in DECISIONS
            or not isinstance(candidate.get("candidate_citations"), list)
            or not all(isinstance(item, str) for item in candidate["candidate_citations"])
            or not isinstance(candidate.get("candidate_expected_facts"), dict)
        ):
            raise ValueError("A pilot candidate has invalid or duplicate fields.")
        seen_ids.add(case_id)
        review_cases.append(
            {
                "case_id": case_id,
                "review_status": "candidate_not_reviewed",
                "candidate_only": True,
                "reviewer_id": "",
                "policy_sha256": policy.sha256,
                "request": request,
                "candidate_decision": candidate["candidate_decision"],
                "candidate_citations": candidate["candidate_citations"],
                "candidate_expected_facts": candidate["candidate_expected_facts"],
                "human_decision": None,
                "expected_citations": [],
                "expected_facts": {},
                "baseline_seconds": None,
                "assisted_seconds": None,
            }
        )

    output_path = Path(output_path)
    try:
        descriptor = os.open(
            output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(
                json.dumps(
                    {
                        "notice": (
                            "Review worksheet generated from synthetic candidates. "
                            "Nothing is marked policy-owner-reviewed. Adjudicate each "
                            "case, populate reviewer/time/expected fields, then set "
                            "review_status to reviewed and candidate_only to false."
                        ),
                        "cases": review_cases,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n"
            )
    except FileExistsError as error:
        raise ValueError("Output file already exists; refusing to overwrite it.") from error
    return len(review_cases)


def evaluate_reviewed_pilot(
    fixture_path: Path, policy_path: Path
) -> dict[str, Any]:
    policy = PolicyTool(policy_path)
    cases = _read_reviewed_cases(fixture_path, policy.sha256)
    details = []
    with tempfile.TemporaryDirectory(prefix="policy-triage-pilot-") as tempdir:
        memory = CaseMemory(Path(tempdir) / "pilot.sqlite3")
        agent = TriageAgent(policy, memory)
        try:
            for record in cases:
                output = agent.triage(record["request"])
                expected_facts = record["expected_facts"]
                input_facts = record["request"]["facts"]
                fact_errors = [
                    field
                    for field, expected in expected_facts.items()
                    if input_facts.get(field) != expected
                    or output["evidence"]["provided_facts"].get(field) != expected
                ]
                expected_citations = set(record["expected_citations"])
                actual_citations = set(output["policy_citations"])
                details.append(
                    {
                        "case_id": record["case_id"],
                        "decision_agreement": (
                            output["recommendation"] == record["human_decision"]
                        ),
                        "citation_precision": (
                            len(actual_citations & expected_citations)
                            / len(actual_citations)
                            if actual_citations
                            else (1.0 if not expected_citations else 0.0)
                        ),
                        "citation_recall": (
                            len(actual_citations & expected_citations)
                            / len(expected_citations)
                            if expected_citations
                            else (1.0 if not actual_citations else 0.0)
                        ),
                        "expected_critical_fact_count": len(expected_facts),
                        "critical_fact_errors": fact_errors,
                        "invalid_facts": output["invalid_facts"],
                        "escalated": output["recommendation"] == "escalate",
                        "overridden": (
                            output["recommendation"] != record["human_decision"]
                        ),
                        "baseline_seconds": record["baseline_seconds"],
                        "assisted_seconds": record["assisted_seconds"],
                    }
                )
        finally:
            memory.close()

    count = len(details)
    total_facts = sum(row["expected_critical_fact_count"] for row in details)
    fact_errors = sum(len(row["critical_fact_errors"]) for row in details)
    baseline_median = statistics.median(row["baseline_seconds"] for row in details)
    assisted_median = statistics.median(row["assisted_seconds"] for row in details)
    time_saved_percent = (
        round((baseline_median - assisted_median) / baseline_median * 100, 2)
        if baseline_median > 0
        else None
    )
    return {
        "status": "measured",
        "source": "policy_owner_reviewed_cases",
        "case_count": count,
        "policy_sha256": policy.sha256,
        "decision_agreement": round(
            sum(row["decision_agreement"] for row in details) / count, 4
        ),
        "citation_precision": round(
            sum(row["citation_precision"] for row in details) / count, 4
        ),
        "citation_recall": round(
            sum(row["citation_recall"] for row in details) / count, 4
        ),
        "critical_fact_error_rate": round(fact_errors / total_facts, 4)
        if total_facts
        else None,
        "critical_fact_error_count": fact_errors,
        "critical_fact_count": total_facts,
        "escalation_rate": round(sum(row["escalated"] for row in details) / count, 4),
        "override_rate": round(sum(row["overridden"] for row in details) / count, 4),
        "median_baseline_seconds": baseline_median,
        "median_assisted_seconds": assisted_median,
        "median_time_saved_percent": time_saved_percent,
        "cases": details,
        "limitations": [
            "Metrics describe only the supplied reviewed cases and are not population guarantees.",
            "Critical fact error rate compares structured input facts with reviewer-adjudicated expected facts; this agent does not extract facts from narratives.",
            "Time measurements are user-entered observations and are not independently verified.",
        ],
    }
