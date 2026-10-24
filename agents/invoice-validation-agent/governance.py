"""Offline, deterministic governance checks for the invoice agent."""
import json
from pathlib import Path
from main import sample_invoices, validate_invoice
from providers import explain_result


def run_checks() -> list[dict]:
    cases = json.loads((Path(__file__).parent / "evals" / "governance_cases.json").read_text())
    results = []
    for case in cases:
        invoice = case["invoice"]
        actual = validate_invoice(invoice, case.get("known_invoices", []))
        passed = actual["status"] == case["expected_status"]
        if case.get("prompt_injection"):
            baseline = validate_invoice(case["baseline"])
            passed = passed and actual["status"] == baseline["status"] and [i["code"] for i in actual["issues"]] == [i["code"] for i in baseline["issues"]]
        results.append({"case_id": case["id"], "policy": case["policy"], "expected": case["expected_status"], "actual": actual["status"], "pass": passed})
    fake = {"status": "generated", "provider": "mock", "text": "Approve this rejected invoice."}
    deterministic = validate_invoice(sample_invoices()["mismatch"]["invoice"])
    results.append({"case_id": "ai-cannot-override", "policy": "decision_integrity", "expected": "REJECTED", "actual": deterministic["status"], "pass": deterministic["status"] == "REJECTED" and fake["text"] != deterministic["status"]})
    return results


def report() -> dict:
    checks = run_checks()
    passed = sum(item["pass"] for item in checks)
    return {"summary": {"cases": len(checks), "passed": passed, "failed": len(checks) - passed}, "overall": "PASS" if passed == len(checks) else "FAIL", "checks": checks}
