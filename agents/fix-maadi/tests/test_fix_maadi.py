import unittest
from unittest.mock import patch

from fix_maadi import analyze, channel_stats
from guardrails import review_case
from privacy import find_sensitive_data, redact_text


class FixMaadiTests(unittest.TestCase):
    def test_routes_waterlogged_pothole_and_requests_landmark(self):
        result = analyze({"description": "deep pothole full of rainwater", "observed_at": "this morning"})
        self.assertEqual(result["category"], "Waterlogging / drainage")
        self.assertIn("Pothole / road damage", result["related_categories"])
        self.assertEqual(result["severity"], "high")
        self.assertIn("a map pin, street, or nearest landmark", result["missing_confirmation"])
        self.assertIn("Sahaaya", result["suggested_channel"])

    def test_garbage_gets_waste_route_and_bilingual_draft(self):
        result = analyze({"description": "Garbage has not been collected for five days", "landmark": "HSR bus stop"})
        self.assertEqual(result["category"], "Garbage / waste")
        self.assertIn("solid-waste", result["suggested_authority"])
        self.assertIn("ವಿಷಯ", result["kannada_draft"])

    def test_duplicate_candidate_is_flagged_without_auto_submission(self):
        result = analyze({
            "description": "broken streetlight near the metro",
            "location": "Indiranagar 100 Feet Road",
            "coordinates": {"latitude": "12.9716", "longitude": "77.6412"},
            "existing_cases": [{"case_id": "FM-OLD", "category": "Streetlight / visibility", "location": "Indiranagar 100 Feet Road"}],
        })
        self.assertIsNone(result["duplicate_candidate"])
        result = analyze({
            "description": "broken streetlight near the metro",
            "coordinates": {"latitude": "12.9716", "longitude": "77.6412"},
            "existing_cases": [{"case_id": "FM-OLD", "category": "Streetlight / visibility", "coordinates": {"latitude": "12.9716", "longitude": "77.6412"}}],
        })
        self.assertEqual(result["duplicate_candidate"]["case_id"], "FM-OLD")
        self.assertNotIn("submit", result)

    def test_same_category_different_places_is_not_a_duplicate(self):
        result = analyze({
            "description": "broken streetlight",
            "location": "Jayanagar 4th Block",
            "observed_at": "tonight",
            "existing_cases": [{"case_id": "FM-OLD", "category": "Streetlight / visibility", "location": "Whitefield Main Road"}],
        })
        self.assertIsNone(result["duplicate_candidate"])

    def test_missing_information_creates_questions_and_agent_state(self):
        result = analyze({"description": "garbage is piling up", "landmark": "HSR bus stop"})
        self.assertEqual(result["status"], "needs_information")
        self.assertIn("duration", [question["field"] for question in result["questions"]])

    def test_complete_case_is_ready_and_has_multi_issue_routes(self):
        result = analyze({
            "description": "A pothole is full of rainwater and blocking the road",
            "location": "12th Main, Indiranagar",
            "observed_at": "today at 9 AM",
        })
        self.assertEqual(result["status"], "ready_for_review")
        self.assertGreaterEqual(len(result["routing_plan"]), 2)
        self.assertTrue(result["routing_plan"][0]["options"])

    def test_waste_route_explains_whatsapp_scope_and_contact(self):
        result = analyze({"description": "Someone is dumping garbage on a vacant site", "location": "HSR Layout", "observed_at": "today", "duration": "one day"})
        whatsapp = next(option for option in result["submission_options"] if option.get("mode") == "whatsapp_handoff")
        self.assertEqual(whatsapp["contact"], "+91 94806 85700")
        self.assertIn("dumping", whatsapp["best_for"].lower())
        self.assertTrue(whatsapp["official"])
        self.assertTrue(whatsapp["recommended"])

    def test_missed_waste_collection_recommends_helpline_not_whatsapp(self):
        result = analyze({"description": "Garbage was not collected this week", "location": "Jayanagar", "observed_at": "today", "duration": "one week"})
        recommended = next(option for option in result["submission_options"] if option.get("recommended"))
        self.assertEqual(recommended["id"], "bbmp-waste-helpline")

    def test_empty_channel_feedback_has_no_fake_efficiency(self):
        stats = channel_stats()
        self.assertIsInstance(stats, dict)

    def test_every_supported_issue_has_a_recommended_sourced_channel(self):
        examples = [
            "large pothole on the road",
            "waterlogging beside a blocked drain",
            "garbage piling up on the street",
            "streetlight is not working",
            "footpath is blocked for wheelchair users",
            "an unidentified public civic concern",
        ]
        for description in examples:
            with self.subTest(description=description):
                result = analyze({"description": description, "location": "Bengaluru", "observed_at": "today", "duration": "two days"})
                options = result["submission_options"]
                recommended = [option for option in options if option.get("recommended")]
                self.assertEqual(len(recommended), 1)
                self.assertTrue(recommended[0].get("official"))
                self.assertTrue(recommended[0].get("source"))
                self.assertTrue(recommended[0].get("id"))

    def test_streetlight_on_dark_road_does_not_invent_pothole(self):
        result = analyze({"description": "Three streetlights are not working and the road is dark", "location": "BTM Layout", "observed_at": "tonight"})
        self.assertEqual(result["category"], "Streetlight / visibility")
        self.assertNotIn("Pothole / road damage", result["related_categories"])

    def test_without_gemini_key_image_path_uses_safe_local_fallback(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}, clear=False):
            result = analyze({"description": "photo attached", "image_data": "not-real", "image_mime": "image/jpeg"})
        self.assertEqual(result["vision_provider"], "local")
        self.assertIn("approval_gate", [item["stage"] for item in result["decision_trace"]])

    def test_guardrails_flag_unsupported_sla_claim(self):
        result = review_case({"english_draft": "This will be fixed within 48 hours.", "kannada_draft": "", "routing_plan": []})
        self.assertFalse(result["passed"])
        self.assertFalse(next(item for item in result["checks"] if item["id"] == "no_promises")["passed"])

    def test_privacy_finds_and_redacts_contact_details(self):
        self.assertEqual(find_sensitive_data("Call +91 98765 43210 or mail me@example.com"), ["phone", "email"])
        self.assertIn("[phone removed]", redact_text("Call +91 98765 43210"))
        self.assertIn("[email removed]", redact_text("mail me@example.com"))

    def test_guardrails_block_unsafe_external_actions(self):
        result = review_case({"english_draft": "", "kannada_draft": "", "routing_plan": [{"options": [{"mode": "captcha_bypass"}]}]})
        self.assertFalse(result["passed"])
        self.assertFalse(next(item for item in result["checks"] if item["id"] == "no_auth_bypass")["passed"])

    def test_guardrails_flag_contact_details_across_case_fields(self):
        result = review_case({"description": "Call +91 98765 43210", "english_draft": "", "kannada_draft": "", "routing_plan": []})
        self.assertFalse(next(item for item in result["checks"] if item["id"] == "privacy_review")["passed"])

    def test_empty_input_is_safe_and_explains_missing_context(self):
        result = analyze({})
        self.assertEqual(result["category"], "General civic issue")
        self.assertEqual(result["confidence"], "low")
        self.assertGreaterEqual(len(result["missing_confirmation"]), 3)


if __name__ == "__main__":
    unittest.main()
