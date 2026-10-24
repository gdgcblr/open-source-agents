"""
Unit Tests for Driver Request Copilot
======================================
Tests all 15 mentor-required scenarios and core safety guardrails using Python's
built-in unittest framework.
"""

import json
import os
import sys
import unittest

# Ensure the parent directory (driver-request-copilot) is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from copilot import (
    DecisionResult,
    DecisionState,
    create_briefing,
    decide,
    evaluate_dataset,
    evaluate_preferences,
    is_valid_numeric,
    load_preferences,
    load_requests,
    validate_preferences,
    validate_request,
)


class TestDriverRequestCopilot(unittest.TestCase):
    """Complete test suite verifying safety precedence, validation, and evaluation."""

    def setUp(self) -> None:
        """Standard valid preferences fixture."""
        self.valid_prefs = {
            "min_fare": 80.0,
            "max_pickup_km": 3.0,
            "avoid_destinations": ["Airport", "Outer Ring Toll"],
        }
        self.base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.dataset_path = os.path.join(self.base_dir, "evaluations", "dataset.json")
        self.prefs_path = os.path.join(self.base_dir, "preferences.json")

    # -------------------------------------------------------------------------
    # Test 1: Valid request returns BRIEF when interaction is explicitly safe
    # -------------------------------------------------------------------------
    def test_01_valid_request_returns_brief_when_safe(self) -> None:
        req = {
            "request_id": "REQ-101",
            "fare": 150.0,
            "pickup_km": 1.5,
            "destination": "Indiranagar",
            "is_safe_to_interact": True,
            "driver_busy": False,
        }
        res = decide(req, self.valid_prefs)
        self.assertEqual(res.state, DecisionState.BRIEF)
        self.assertIsNotNone(res.briefing)
        self.assertIn("MATCHES ALL SAVED PREFERENCES", res.briefing)
        self.assertIn("Indiranagar", res.briefing)

    # -------------------------------------------------------------------------
    # Test 2: Request below minimum fare is correctly explained
    # -------------------------------------------------------------------------
    def test_02_request_below_min_fare_explained(self) -> None:
        req = {
            "fare": 50.0,
            "pickup_km": 1.5,
            "destination": "Koramangala",
            "is_safe_to_interact": True,
            "driver_busy": False,
        }
        res = decide(req, self.valid_prefs)
        self.assertEqual(res.state, DecisionState.BRIEF)
        self.assertEqual(res.reason_code, "PREFERENCE_MISMATCH")
        self.assertIn("Fare Alert: Rs. 50.0 is Rs. 30.0 below minimum Rs. 80.0", res.briefing)

    # -------------------------------------------------------------------------
    # Test 3: Pickup distance above configured limit is correctly explained
    # -------------------------------------------------------------------------
    def test_03_pickup_distance_above_limit_explained(self) -> None:
        req = {
            "fare": 120.0,
            "pickup_km": 5.2,
            "destination": "MG Road",
            "is_safe_to_interact": True,
            "driver_busy": False,
        }
        res = decide(req, self.valid_prefs)
        self.assertEqual(res.state, DecisionState.BRIEF)
        self.assertEqual(res.reason_code, "PREFERENCE_MISMATCH")
        self.assertIn("Pickup Alert: 5.2 km exceeds your 3.0 km limit by 2.2 km", res.briefing)

    # -------------------------------------------------------------------------
    # Test 4: Avoided destination is detected
    # -------------------------------------------------------------------------
    def test_04_avoided_destination_detected(self) -> None:
        req = {
            "fare": 500.0,
            "pickup_km": 1.0,
            "destination": "Airport",
            "is_safe_to_interact": True,
            "driver_busy": False,
        }
        res = decide(req, self.valid_prefs)
        self.assertEqual(res.state, DecisionState.BRIEF)
        self.assertEqual(res.reason_code, "PREFERENCE_MISMATCH")
        self.assertIn("Destination Alert: 'Airport' is in your avoided destinations list", res.briefing)

    # -------------------------------------------------------------------------
    # Test 5: Missing fare returns CLARIFY
    # -------------------------------------------------------------------------
    def test_05_missing_fare_returns_clarify(self) -> None:
        req = {
            "pickup_km": 1.8,
            "destination": "Whitefield",
            "is_safe_to_interact": True,
            "driver_busy": False,
        }
        res = decide(req, self.valid_prefs)
        self.assertEqual(res.state, DecisionState.CLARIFY)
        self.assertIsNone(res.briefing)
        self.assertIn("fare", res.explanation.lower())

    # -------------------------------------------------------------------------
    # Test 6: Missing destination returns CLARIFY
    # -------------------------------------------------------------------------
    def test_06_missing_or_blank_destination_returns_clarify(self) -> None:
        # Blank whitespace destination
        req1 = {
            "fare": 100.0,
            "pickup_km": 1.0,
            "destination": "   ",
            "is_safe_to_interact": True,
            "driver_busy": False,
        }
        res1 = decide(req1, self.valid_prefs)
        self.assertEqual(res1.state, DecisionState.CLARIFY)
        self.assertIsNone(res1.briefing)

        # Missing destination key
        req2 = {
            "fare": 100.0,
            "pickup_km": 1.0,
            "is_safe_to_interact": True,
            "driver_busy": False,
        }
        res2 = decide(req2, self.valid_prefs)
        self.assertEqual(res2.state, DecisionState.CLARIFY)
        self.assertIsNone(res2.briefing)

    # -------------------------------------------------------------------------
    # Test 7: Invalid or negative distance returns CLARIFY
    # -------------------------------------------------------------------------
    def test_07_invalid_or_negative_distance_returns_clarify(self) -> None:
        req = {
            "fare": 110.0,
            "pickup_km": -2.5,
            "destination": "HSR Layout",
            "is_safe_to_interact": True,
            "driver_busy": False,
        }
        res = decide(req, self.valid_prefs)
        self.assertEqual(res.state, DecisionState.CLARIFY)
        self.assertIsNone(res.briefing)
        self.assertIn("cannot be negative", res.explanation.lower())

    # -------------------------------------------------------------------------
    # Test 8: Wrongly typed fare returns CLARIFY
    # -------------------------------------------------------------------------
    def test_08_wrongly_typed_fare_returns_clarify(self) -> None:
        req = {
            "fare": "one hundred",
            "pickup_km": 2.0,
            "destination": "Hebbal",
            "is_safe_to_interact": True,
            "driver_busy": False,
        }
        res = decide(req, self.valid_prefs)
        self.assertEqual(res.state, DecisionState.CLARIFY)
        self.assertIsNone(res.briefing)
        self.assertIn("numeric", res.explanation.lower())

    # -------------------------------------------------------------------------
    # Test 9: Unsafe or busy interaction returns DEFER when validation passes
    # -------------------------------------------------------------------------
    def test_09_unsafe_or_busy_interaction_returns_defer(self) -> None:
        req = {
            "fare": 180.0,
            "pickup_km": 1.2,
            "destination": "Jayanagar",
            "is_safe_to_interact": False,
            "driver_busy": True,
        }
        res = decide(req, self.valid_prefs)
        self.assertEqual(res.state, DecisionState.DEFER)
        self.assertIsNone(res.briefing)
        self.assertIn("deferred", res.explanation.lower())

    # -------------------------------------------------------------------------
    # Test 10: Invalid preferences return HALT
    # -------------------------------------------------------------------------
    def test_10_invalid_preferences_return_halt(self) -> None:
        bad_prefs = {
            "min_fare": -10.0,  # Negative min_fare
            "max_pickup_km": 3.0,
            "avoid_destinations": ["Airport"],
        }
        req = {
            "fare": 150.0,
            "pickup_km": 1.5,
            "destination": "Indiranagar",
            "is_safe_to_interact": True,
            "driver_busy": False,
        }
        res = decide(req, bad_prefs)
        self.assertEqual(res.state, DecisionState.HALT)
        self.assertEqual(res.reason_code, "CONFIG_INVALID")
        self.assertIsNone(res.briefing)

    # -------------------------------------------------------------------------
    # Test 11: Invalid JSON or unexpected input structure fails safely
    # -------------------------------------------------------------------------
    def test_11_unexpected_structure_fails_safely_as_halt(self) -> None:
        bad_req = "NOT_A_DICTIONARY"
        res = decide(bad_req, self.valid_prefs)
        self.assertEqual(res.state, DecisionState.HALT)
        self.assertEqual(res.reason_code, "STRUCTURAL_MALFORMED")

    # -------------------------------------------------------------------------
    # Test 12: Conflict between missing data and unsafe interaction follows priority
    # -------------------------------------------------------------------------
    def test_12_conflict_data_invalid_and_unsafe_follows_precedence(self) -> None:
        # Request is missing fare AND interaction is unsafe/busy
        req = {
            "pickup_km": 2.0,
            "destination": "Electronic City",
            "is_safe_to_interact": False,
            "driver_busy": True,
        }
        res = decide(req, self.valid_prefs)
        # Precedence: CLARIFY precedes DEFER
        self.assertEqual(res.state, DecisionState.CLARIFY)
        self.assertEqual(res.reason_code, "DATA_INVALID")

    # -------------------------------------------------------------------------
    # Test 13: System never returns ride-acceptance or ride-rejection action
    # -------------------------------------------------------------------------
    def test_13_never_executes_autonomous_ride_actions(self) -> None:
        req = {
            "fare": 200.0,
            "pickup_km": 0.5,
            "destination": "Indiranagar",
            "is_safe_to_interact": True,
            "driver_busy": False,
        }
        res = decide(req, self.valid_prefs)
        # Verify result contains no autonomous accept/reject command
        res_dict = res.to_dict()
        self.assertNotIn("accept", res_dict.get("state", "").lower())
        self.assertNotIn("reject", res_dict.get("state", "").lower())
        # Verify reminder in briefing
        self.assertIn("Driver retains final decision", res.briefing)

    # -------------------------------------------------------------------------
    # Test 14: Evaluation script reports expected decisions accurately
    # -------------------------------------------------------------------------
    def test_14_evaluation_dataset_accuracy_and_metrics(self) -> None:
        report = evaluate_dataset(self.dataset_path, self.prefs_path)
        self.assertEqual(report.total_cases, 14)
        self.assertEqual(report.passed_cases, 14)
        self.assertEqual(report.failed_cases, 0)
        self.assertEqual(report.safety_violations, 0)
        self.assertEqual(report.overall_accuracy, 1.0)
        # Verify each class has non-zero support
        for state in [DecisionState.HALT.value, DecisionState.CLARIFY.value, DecisionState.DEFER.value, DecisionState.BRIEF.value]:
            self.assertGreater(report.class_metrics[state]["support"], 0)
            self.assertEqual(report.class_metrics[state]["precision"], 1.0)
            self.assertEqual(report.class_metrics[state]["recall"], 1.0)

    # -------------------------------------------------------------------------
    # Test 15: Briefing function does not invent facts absent from request
    # -------------------------------------------------------------------------
    def test_15_briefing_is_strictly_grounded(self) -> None:
        req = {
            "request_id": "REQ-777",
            "fare": 95.5,
            "pickup_km": 2.1,
            "destination": "Ulsoor Lake",
        }
        eval_res = evaluate_preferences(req, self.valid_prefs)
        briefing = create_briefing(req, self.valid_prefs, eval_res)

        # Values present in request must appear exactly
        self.assertIn("95.5", briefing)
        self.assertIn("2.1", briefing)
        self.assertIn("Ulsoor Lake", briefing)
        self.assertIn("REQ-777", briefing)

        # Values NOT in request must NEVER appear
        self.assertNotIn("traffic delay", briefing.lower())
        self.assertNotIn("passenger rating", briefing.lower())
        self.assertNotIn("surge 2.0x", briefing.lower())

    # -------------------------------------------------------------------------
    # Additional Guardrail Test: Python bool as int subclass edge case
    # -------------------------------------------------------------------------
    def test_16_boolean_as_numeric_field_rejected(self) -> None:
        self.assertFalse(is_valid_numeric(True))
        self.assertFalse(is_valid_numeric(False))

        req = {
            "fare": True,
            "pickup_km": 1.5,
            "destination": "MG Road",
            "is_safe_to_interact": True,
            "driver_busy": False,
        }
        res = decide(req, self.valid_prefs)
        self.assertEqual(res.state, DecisionState.CLARIFY)
        self.assertIn("numeric", res.explanation.lower())


if __name__ == "__main__":
    unittest.main()
