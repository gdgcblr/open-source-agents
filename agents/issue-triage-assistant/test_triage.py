import json
import unittest

import triage


class TriageTests(unittest.TestCase):
    def result(self, **updates):
        value = {**triage.MOCK_RESULT, "evidence": [*triage.MOCK_RESULT["evidence"]]}
        value.update(updates)
        return value

    def test_validation_keeps_exact_issue_quotes_and_allowlisted_labels(self):
        value = self.result(
            suggested_labels=["bug", "made-up-label"],
            evidence=[
                {"field": "summary", "quote": "Export crashes when saving a report"},
                {"field": "summary", "quote": "It crashes"},
            ],
        )
        actual = triage.validate_result(
            value,
            "Export crashes when saving a report.",
            ["bug"],
        )
        self.assertEqual(actual["suggested_labels"], ["bug"])
        self.assertEqual(len(actual["evidence"]), 1)
        self.assertEqual(actual["evidence"][0]["quote"], "Export crashes when saving a report")

    def test_missing_template_field_forces_needs_information(self):
        value = self.result(
            missing_information=[],
            readiness="ready",
            template_checks=[{"field": "Steps to reproduce", "status": "missing"}],
        )
        actual = triage.validate_result(
            value,
            "Export crashes.",
            [],
            ["Steps to reproduce"],
        )
        self.assertEqual(actual["readiness"], "needs_information")
        self.assertIn("Steps to reproduce", actual["missing_information"])

    def test_unknown_template_fields_are_discarded(self):
        value = self.result(template_checks=[{"field": "Private field", "status": "missing"}])
        actual = triage.validate_result(value, "Export crashes.", [], ["Steps to reproduce"])
        self.assertEqual(actual["template_checks"], [])

    def test_repository_labels_are_not_reporter_information(self):
        value = self.result(missing_information=["Repository labels"], readiness="needs_information")
        actual = triage.validate_result(value, "Add Cloudflare to the hosting docs.", ["docs"])
        self.assertEqual(actual["missing_information"], [])
        self.assertEqual(actual["readiness"], "ready")

    def test_empty_evidence_falls_back_to_exact_issue_title(self):
        value = self.result(evidence=[])
        actual = triage.validate_result(
            value,
            "Title: Add Cloudflare to the Hosting Platforms docs\n\nCould we add a link to this page?",
        )
        self.assertEqual(
            actual["evidence"],
            [{"field": "issue summary", "quote": "Add Cloudflare to the Hosting Platforms docs"}],
        )

    def test_empty_draft_and_guidance_get_helpful_fallbacks(self):
        value = self.result(
            summary="Add Cloudflare to the Hosting Platforms docs.",
            maintainer_guidance="  ",
            draft_reply="\n ",
            missing_information=[],
            readiness="ready",
        )
        actual = triage.validate_result(value, "Could we add a Cloudflare link to the docs?")
        self.assertIn("review it", actual["maintainer_guidance"].casefold())
        self.assertIn("Thanks for the suggestion", actual["draft_reply"])
        self.assertTrue(actual["draft_reply"].strip())

    def test_omitted_draft_fields_get_fallbacks(self):
        value = self.result()
        value.pop("draft_reply")
        value.pop("maintainer_guidance")
        actual = triage.validate_result(value, "Export crashes.")
        self.assertTrue(actual["draft_reply"])
        self.assertTrue(actual["maintainer_guidance"])

    def test_rejects_missing_required_fields(self):
        with self.assertRaises(ValueError):
            triage.validate_result({"summary": "Only a summary"}, "issue")

    def test_rejects_non_string_list_items(self):
        value = self.result(suggested_labels=["bug", 4])
        with self.assertRaises(ValueError):
            triage.validate_result(value, "Export crashes.")

    def test_parse_json_allows_code_fence(self):
        self.assertEqual(triage._parse_json("```json\n{\"ok\": true}\n```"), {"ok": True})

    def test_render_shows_readiness_and_evidence(self):
        output = triage.render(triage.validate_result(
            triage.MOCK_RESULT,
            "Export crashes when saving a report.",
            ["bug", "needs-reproduction"],
        ))
        self.assertIn("Triage readiness: needs_information", output)
        self.assertIn("Maintainer guidance:", output)
        self.assertIn('summary: "Export crashes when saving a report"', output)

    def test_triage_passes_issue_labels_and_template_context_to_adk(self):
        output = self.result(
            suggested_labels=["bug", "not-allowed"],
            template_checks=[{"field": "Steps to reproduce", "status": "present"}],
        )
        prompts = []

        def fake_responder(prompt, model, host):
            prompts.append(prompt)
            return json.dumps(output)

        actual = triage.triage(
            "Export crashes with steps to reproduce included.",
            "http://localhost:11434",
            "llama3.2:3b",
            ["bug"],
            "## Steps to reproduce\nDescribe the steps.",
            responder=fake_responder,
        )
        self.assertEqual(actual["suggested_labels"], ["bug"])
        self.assertEqual(actual["template_checks"], [{"field": "Steps to reproduce", "status": "present"}])
        context = json.loads(prompts[0].split("\n", 2)[2])
        self.assertIn("Export crashes", context["issue_text"])
        self.assertEqual(context["allowed_repository_labels"], ["bug"])
        self.assertEqual(context["template_headings_to_check"], ["Steps to reproduce"])


if __name__ == "__main__":
    unittest.main()
