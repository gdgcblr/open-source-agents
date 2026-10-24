"""Unit tests for deterministic compatibility evaluation and verification states."""

from __future__ import annotations

from analysis.compatibility import evaluate_compatibility
from analysis.consumer_usage import extract_consumer_field_accesses
from analysis.contract_extractor import compare_contracts
from domain.models import TestExecutionResult


def test_inferred_risk_vs_reproduced_failure_distinction() -> None:
    before = {"customer_id": "cus_123", "status": "active"}
    after = {"customerId": "cus_123", "status": "active"}
    comp = compare_contracts(before, after)
    accesses = extract_consumer_field_accesses('def f(p):\n    return p["customer_id"]\n')

    # Before test execution -> must be labelled INFERRED_RISK ("Potential compatibility issue")
    findings_pre = evaluate_compatibility(
        provider_repo="orders-api",
        consumer_repo="checkout-client",
        contract_comparison=comp,
        consumer_accesses=accesses,
        combined_test_result=None,
    )
    assert len(findings_pre) == 1
    assert findings_pre[0].verification_state == "INFERRED_RISK"
    assert "Potential compatibility issue" in findings_pre[0].summary

    # After executed combined test fails -> upgraded to REPRODUCED_FAILURE
    failed_test = TestExecutionResult(
        test_id="customer_id_rename:combined_integration",
        label="Combined Integration Test",
        test_kind="combined_integration",
        status="FAIL",
        exit_code=1,
        duration_ms=120,
        stdout="",
        stderr="",
        file_path="repos/checkout-client/tests/test_combined_contract.py",
        failure_summary="KeyError: 'customer_id'",
    )
    findings_post = evaluate_compatibility(
        provider_repo="orders-api",
        consumer_repo="checkout-client",
        contract_comparison=comp,
        consumer_accesses=accesses,
        combined_test_result=failed_test,
    )
    assert len(findings_post) == 1
    assert findings_post[0].verification_state == "REPRODUCED_FAILURE"
    assert "Reproduced integration failure" in findings_post[0].summary
    assert any(ev.kind == "test_execution" for ev in findings_post[0].evidence)


def test_unconsumed_non_required_field_removal_does_not_alert() -> None:
    before = {"customer_id": "cus_123", "internal_trace_id": "tr_99"}
    after = {"customer_id": "cus_123"}
    comp = compare_contracts(before, after, required_fields=["customer_id"])
    accesses = extract_consumer_field_accesses('def f(p):\n    return p["customer_id"]\n')

    findings = evaluate_compatibility(
        provider_repo="orders-api",
        consumer_repo="checkout-client",
        contract_comparison=comp,
        consumer_accesses=accesses,
    )
    assert findings == []


def test_type_incompatibility_detected_with_high_severity_when_consumed() -> None:
    before = {"customer_id": "cus_123", "total_cents": 1200}
    after = {"customer_id": "cus_123", "total_cents": "1200"}
    comp = compare_contracts(before, after)
    accesses = extract_consumer_field_accesses('def f(p):\n    return p["total_cents"] + 100\n')

    findings = evaluate_compatibility(
        provider_repo="orders-api",
        consumer_repo="checkout-client",
        contract_comparison=comp,
        consumer_accesses=accesses,
    )
    assert len(findings) == 1
    assert findings[0].kind == "FIELD_TYPE_CHANGED"
    assert findings[0].severity == "HIGH"
    assert findings[0].field == "total_cents"
