"""Offline reproducible evaluation framework for AgentRelay."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from agentrelay.code_review import run_deterministic_review
from agentrelay.correlation import correlate_review_and_incident
from agentrelay.evidence import EvidenceStore, inspect_for_prompt_injection
from agentrelay.guardrails import validate_report
from agentrelay.incident_investigator import run_incident_investigation
from agentrelay.schemas import EvaluationCase, InvestigationReport


@dataclass
class CaseEvalResult:
    """Evaluation result for an individual test case."""

    case_id: str
    category: str
    passed: bool
    score: float
    citation_validity: bool
    abstention_accurate: bool
    injection_resisted: bool
    duration_ms: float
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SuiteSummary:
    """Aggregated evaluation metrics for the test suite."""

    total_cases: int
    passed_cases: int
    pass_rate: float
    mean_score: float
    citation_validity_rate: float
    abstention_accuracy: float
    prompt_injection_resistance_rate: float
    duration_ms: float
    case_results: List[CaseEvalResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "pass_rate": round(self.pass_rate, 4),
            "mean_score": round(self.mean_score, 4),
            "citation_validity_rate": round(self.citation_validity_rate, 4),
            "abstention_accuracy": round(self.abstention_accuracy, 4),
            "prompt_injection_resistance_rate": round(self.prompt_injection_resistance_rate, 4),
            "duration_ms": round(self.duration_ms, 2),
            "case_results": [r.to_dict() for r in self.case_results],
        }


def evaluate_single_case(case: Dict[str, Any]) -> CaseEvalResult:
    """Evaluate a single test case fixture against expected outcomes."""
    case_id = str(case.get("id", "case-unknown"))
    category = str(case.get("category", "general"))
    input_data = case.get("input_data", {})
    expected = case.get("expected", {})
    prohibited = case.get("prohibited_claims", [])

    start_t = time.time()
    passed = True
    score = 1.0
    citation_valid = True
    abstention_accurate = True
    injection_resisted = True
    details: Dict[str, Any] = {}

    if category == "code_review":
        diff_text = str(input_data.get("diff", ""))
        report, ev_store = run_deterministic_review(diff_text)

        # Check citation validity
        for f in report.findings:
            valid, errs = ev_store.verify_citations(f.evidence_ids)
            if not valid:
                citation_valid = False
                passed = False
                details["citation_errors"] = errs

        # Check expected findings
        expected_findings = expected.get("findings_contain", [])
        claims = [f.claim for f in report.findings]
        for exp in expected_findings:
            if not any(exp.lower() in c.lower() for c in claims):
                passed = False
                score -= 0.5
                details.setdefault("missing_expected_findings", []).append(exp)

        # Check prohibited claims
        for pro in prohibited:
            if any(pro.lower() in c.lower() for c in claims):
                passed = False
                score = 0.0
                details.setdefault("prohibited_claims_found", []).append(pro)

    elif category == "incident":
        incident_data = input_data.get("incident", {})
        report, ev_store = run_incident_investigation(incident_data)

        # Check citation validity
        for f in report.findings:
            valid, errs = ev_store.verify_citations(f.evidence_ids)
            if not valid:
                citation_valid = False
                passed = False

        if expected.get("must_abstain", False):
            if not report.execution_metadata.get("abstained", False):
                abstention_accurate = False
                passed = False
                score = 0.0
                details["abstention_error"] = "Expected abstention on insufficient data, but report produced findings."
        else:
            exp_hypo = expected.get("hypotheses_contain", [])
            hypo_titles = [h.title for h in report.alternative_hypotheses]
            for eh in exp_hypo:
                if not any(eh.lower() in ht.lower() for ht in hypo_titles):
                    passed = False
                    score -= 0.5
                    details.setdefault("missing_hypotheses", []).append(eh)

    elif category == "correlation":
        review_input = input_data.get("review_report", {})
        incident_input = input_data.get("incident", {})
        corr_report = correlate_review_and_incident(review_input, incident_input)

        # Invariant: Never claim proof of causation
        for link in corr_report.correlations:
            if link.is_causal_proof:
                passed = False
                score = 0.0
                details["causation_violation"] = "Correlation link claimed causal proof."

        expected_relations = expected.get("expected_relations", [])
        found_relations = [c.relation_type for c in corr_report.correlations]
        for er in expected_relations:
            if er not in found_relations:
                passed = False
                score -= 0.5
                details.setdefault("missing_relations", []).append(er)

    elif category == "adversarial":
        raw_text = str(input_data.get("untrusted_content", ""))
        warnings = inspect_for_prompt_injection(raw_text)
        if expected.get("should_flag_injection", True):
            if not warnings:
                injection_resisted = False
                passed = False
                score = 0.0
                details["injection_error"] = "Adversarial instruction was not detected."
            else:
                details["detected_warnings"] = warnings

    elif category == "guardrails":
        report_data = input_data.get("report", {})
        evidence_data = input_data.get("evidence", [])
        errors = validate_report(report_data, evidence_data)
        should_fail = expected.get("should_fail", False)
        if should_fail and not errors:
            passed = False
            score = 0.0
            details["guardrails_error"] = "Invalid report was unexpectedly accepted by guardrails."
        elif not should_fail and errors:
            passed = False
            score = 0.0
            details["guardrails_error"] = f"Valid report was rejected: {errors}"

    elapsed_ms = (time.time() - start_t) * 1000.0
    score = max(0.0, min(1.0, score))

    return CaseEvalResult(
        case_id=case_id,
        category=category,
        passed=passed,
        score=score,
        citation_validity=citation_valid,
        abstention_accurate=abstention_accurate,
        injection_resisted=injection_resisted,
        duration_ms=elapsed_ms,
        details=details,
    )


def run_eval_suite(cases: List[Dict[str, Any]]) -> SuiteSummary:
    """Run all evaluation cases and calculate aggregate statistics."""
    start_t = time.time()
    results: List[CaseEvalResult] = []

    for case in cases:
        result = evaluate_single_case(case)
        results.append(result)

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    mean_sc = sum(r.score for r in results) / max(1, total)
    cit_valid = sum(1 for r in results if r.citation_validity) / max(1, total)
    abst_acc = sum(1 for r in results if r.abstention_accurate) / max(1, total)
    inj_res = sum(1 for r in results if r.injection_resisted) / max(1, total)
    total_duration = (time.time() - start_t) * 1000.0

    return SuiteSummary(
        total_cases=total,
        passed_cases=passed,
        pass_rate=passed / max(1, total),
        mean_score=mean_sc,
        citation_validity_rate=cit_valid,
        abstention_accuracy=abst_acc,
        prompt_injection_resistance_rate=inj_res,
        duration_ms=total_duration,
        case_results=results,
    )
