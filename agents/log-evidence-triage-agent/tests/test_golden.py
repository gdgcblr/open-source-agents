"""Named golden checks; fixture outcomes are independent of implementation data."""
from datetime import date
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from incident_triage.config import PROJECT_ROOT
from incident_triage.credibility import citations_valid
from incident_triage.investigation import investigate
from incident_triage.engine import redact, MAX_EXCERPT

TODAY = date(2026, 10, 24)
CASES = json.loads((PROJECT_ROOT / "evaluations/golden.json").read_text())


class GoldenTests(unittest.TestCase):
    pass


def golden_check(case, metric):
    def check(self):
        def run():
            with patch.dict("os.environ", {}, clear=True):
                return investigate(case["log"], case["product"], case["version"], case.get("internet_facing", False),
                                   catalog_path=Path("does-not-exist.json") if case.get("missing_catalog") else None,
                                   today=date.fromisoformat(case["as_of"]) if "as_of" in case else TODAY)
        report = run()
        if metric == "version_match":
            self.assertEqual(report["runtime"]["status"], case["status"])
        elif metric in {"decision_accuracy", "critical_escalation_recall"}:
            self.assertEqual(report["decision"], case["decision"])
            if case["decision"] == "ESCALATE":
                self.assertTrue(report["escalation"]["required"])
                self.assertTrue(report["escalation"]["evidence_refs"])
                for field in ["summary", "severity", "rationale", "unknowns", "assumptions", "next_steps", "required_human_decision"]:
                    self.assertIn(field, report["escalation"])
        elif metric == "citation_validity":
            self.assertTrue(citations_valid(report))
            for evidence in report["evidence"].values():
                if evidence["kind"] == "log":
                    self.assertLessEqual(evidence["line"], len(case["log"].splitlines()))
                    self.assertEqual(evidence["excerpt"], redact(case["log"].splitlines()[evidence["line"] - 1])[:MAX_EXCERPT])
        elif metric == "no_unsupported_compromise":
            self.assertEqual(report["compromise"], "NOT_CONFIRMED")
        elif metric == "deterministic_consistency":
            self.assertEqual(report, run())
        elif metric == "indicator_detection":
            self.assertIn(case["kind"], [f["kind"] for f in report["findings"]])
        elif metric == "secret_redaction":
            self.assertNotIn(case["secret"], json.dumps(report))
        elif metric == "overall_security_unknown":
            self.assertEqual(report["runtime"]["overall_security"], "OVERALL_SECURITY_UNKNOWN")
            self.assertIn("OVERALL_SECURITY_UNKNOWN", report["summary"])
            self.assertTrue(report["coverage_warnings"])
            # Raw logs can contain an attacker's claim of safety; canonical findings cannot.
            self.assertNotRegex(" ".join(f["text"] for f in report["findings"]), r"(?i)\b(?:is secure|is safe|no vulnerabilities|fully patched)\b")
            if "freshness" in case:
                self.assertEqual(report["runtime"]["freshness"]["status"], case["freshness"])
            if "coverage_gap" in case:
                self.assertIn(case["coverage_gap"], [g["code"] for g in report["runtime"]["coverage_gaps"]])
    check.metric = metric
    return check


for case in CASES:
    metrics = ["version_match", "decision_accuracy", "citation_validity", "no_unsupported_compromise", "deterministic_consistency", "overall_security_unknown"]
    if case["decision"] == "ESCALATE":
        metrics.append("critical_escalation_recall")
    if "kind" in case:
        metrics.append("indicator_detection")
    if "secret" in case:
        metrics.append("secret_redaction")
    for metric in metrics:
        setattr(GoldenTests, f"test_{case['id']}_{metric}", golden_check(case, metric))
