"""Advisory-specific fixes must never become an overall security verdict."""
from datetime import date
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from incident_triage.ai import model_bundle
from incident_triage.config import PROJECT_ROOT
from incident_triage.credibility import apply_candidate
from incident_triage.investigation import investigate


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_freshness_boundary_is_explicit(self):
        for day, freshness, decision in [(31, "FRESH", "PASS"), (None, "STALE", "HOLD")]:
            today = date(2026, 10, day) if day else date(2026, 11, 1)
            r = investigate("INFO ready", "nodejs", "22.23.4", today=today)
            self.assertEqual(r["decision"], decision)
            self.assertEqual(r["runtime"]["freshness"], {
                "status": freshness, "evaluated_on": today.isoformat(), "verified_on": "2026-10-24",
                "age_days": 7 if day else 8, "max_age_days": 7})
            self.assertIn("AFTER_VERIFICATION", [g["code"] for g in r["runtime"]["coverage_gaps"]])

    def test_partial_branch_coverage_cannot_hide_unevaluated_advisory(self):
        catalog = json.loads((PROJECT_ROOT / "data/advisories.json").read_text())
        # Synthetic coverage omission; no change to the production advisory facts.
        catalog["records"][1]["ranges"] = catalog["records"][1]["ranges"][-1:]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(catalog))
            r = investigate("INFO ready", "php", "8.4.27", catalog_path=path, today=date(2026, 10, 24))
        self.assertEqual(r["runtime"]["status"], "UNKNOWN")
        self.assertEqual(r["decision"], "HOLD")
        self.assertEqual(r["runtime"]["checked_advisory_ids"], ["CVE-2026-109618"])
        gap = next(g for g in r["runtime"]["coverage_gaps"] if g["code"] == "UNEVALUATED_ADVISORY")
        self.assertEqual(gap["cve"], "CVE-2026-109619")
        self.assertEqual(gap["published"], "2026-10-21")

    def test_newer_notice_is_separate_from_fixed_cves(self):
        r = investigate("INFO ready", "php", "8.4.27", today=date(2026, 10, 24))
        self.assertEqual(r["runtime"]["status"], "FIXED_FOR_CHECKED_ADVISORIES")
        self.assertTrue(all(m["status"] == "FIXED" and m["published"] == "2026-10-21" for m in r["runtime"]["matches"]))
        gap = next(g for g in r["runtime"]["coverage_gaps"] if g["code"] == "UNEVALUATED_NOTICE")
        self.assertTrue(gap["newer_than_curated_advisories"])
        self.assertEqual(gap["published"], "2026-10-23")
        self.assertTrue(gap["requires_hold"])
        self.assertEqual(r["decision"], "HOLD")

    def test_blanket_secure_model_claim_rejected_despite_real_citations(self):
        r = investigate("INFO ready", "nodejs", "22.23.4", today=date(2026, 10, 24))
        candidate = model_bundle(r)
        candidate["claims"][0]["text"] = "This runtime is secure and has no vulnerabilities."
        result = apply_candidate(r, candidate)
        self.assertEqual(result["decision"], "HOLD")
        self.assertEqual(result["runtime"]["overall_security"], "OVERALL_SECURITY_UNKNOWN")
        self.assertNotIn("This runtime is secure", json.dumps(result))

    def test_ai_selection_cannot_remove_coverage_warning(self):
        r = investigate("INFO ready", "nodejs", "22.23.4", today=date(2026, 10, 24))
        candidate = model_bundle(r)
        candidate["claims"] = candidate["claims"][:1]
        result = apply_candidate(r, candidate)
        self.assertEqual(result["mode"], "ai_assisted_validated")
        self.assertEqual(result["coverage_warnings"], r["coverage_warnings"])
        self.assertIn("coverage", [f["kind"] for f in result["findings"]])
        self.assertEqual(result["runtime"]["overall_security"], "OVERALL_SECURITY_UNKNOWN")


for name in [n for n in dir(CoverageTests) if n.startswith("test_")]:
    getattr(CoverageTests, name).metric = "advisory_coverage_safety"
