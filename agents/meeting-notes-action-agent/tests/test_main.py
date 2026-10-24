import json
import sys
from types import ModuleType
from unittest.mock import Mock, patch
import unittest

from main import analyze_notes, normalize_analysis


class NormalizeAnalysisTests(unittest.TestCase):
    def test_normalizes_valid_analysis(self):
        result = normalize_analysis(
            {
                "summary": "The team agreed to ship the update.",
                "decisions": ["Ship the update on Friday."],
                "action_items": [{"task": "Prepare release notes"}],
                "open_questions": [],
            }
        )

        self.assertEqual(result["action_items"][0]["owner"], None)
        self.assertEqual(result["action_items"][0]["due_date"], None)
        self.assertEqual(result["decisions"], ["Ship the update on Friday."])

    def test_rejects_action_item_without_task(self):
        with self.assertRaisesRegex(ValueError, "string 'task'"):
            normalize_analysis(
                {
                    "summary": "Summary",
                    "decisions": [],
                    "action_items": [{"owner": "Alex"}],
                    "open_questions": [],
                }
            )

    def test_rejects_non_string_decisions(self):
        with self.assertRaisesRegex(ValueError, "list of strings"):
            normalize_analysis(
                {
                    "summary": "Summary",
                    "decisions": [123],
                    "action_items": [],
                    "open_questions": [],
                }
            )


class AnalyzeNotesTests(unittest.TestCase):
    def test_sends_notes_to_model_and_normalizes_json_response(self):
        expected = {
            "summary": "The team agreed on a launch date.",
            "decisions": ["Launch Friday."],
            "action_items": [{"task": "Prepare the announcement"}],
            "open_questions": [],
        }
        client = Mock()
        client.models.generate_content.return_value.text = json.dumps(expected)

        google_module = ModuleType("google")
        genai_module = ModuleType("google.genai")
        types_module = ModuleType("google.genai.types")
        genai_module.__path__ = []
        config_factory = Mock(return_value=object())
        types_module.GenerateContentConfig = config_factory
        genai_module.types = types_module
        genai_module.Client = Mock(return_value=client)
        google_module.genai = genai_module

        with patch.dict(
            sys.modules,
            {
                "google": google_module,
                "google.genai": genai_module,
                "google.genai.types": types_module,
            },
        ):
            result = analyze_notes("Launch Friday.", "test-key", "test-model")

        self.assertEqual(result["summary"], expected["summary"])
        self.assertIsNone(result["action_items"][0]["owner"])
        client.models.generate_content.assert_called_once()
        request = client.models.generate_content.call_args.kwargs
        self.assertEqual(request["model"], "test-model")
        self.assertIn("Launch Friday.", request["contents"])
        config_factory.assert_called_once_with(response_mime_type="application/json")

if __name__ == "__main__":
    unittest.main()