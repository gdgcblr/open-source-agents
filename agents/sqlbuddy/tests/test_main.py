
import unittest
from unittest.mock import patch

import main


class TestSQLBuddy(unittest.TestCase):

    def test_menu_displays_four_options(self):
        with patch("builtins.print") as mock_print:
            main.show_menu()

        printed_text = " ".join(
            str(call) for call in mock_print.call_args_list
        )

        self.assertIn("Convert English to SQL", printed_text)
        self.assertIn("Explain an SQL query", printed_text)
        self.assertIn("Help with an SQL error", printed_text)
        self.assertIn("Exit", printed_text)

    def test_missing_api_key_message(self):
        with patch.object(main, "API_KEY", None), patch.dict(
            "os.environ", {"GEMINI_API_KEY": ""}
        ):
            result = main.ask_gemini("Generate a SQL query")

        self.assertIn("API key not configured", result)

    def test_api_key_placeholder_message(self):
        with patch.object(main, "API_KEY", "your_api_key_here"):
            result = main.ask_gemini("Generate a SQL query")

        self.assertIn("API key not configured", result)

    def test_empty_prompt_is_rejected_before_api_call(self):
        with patch.object(main, "genai") as genai:
            self.assertIn("non-empty", main.ask_gemini("  "))
        genai.Client.assert_not_called()

    def test_successful_response_is_trimmed(self):
        response = type("Response", (), {"text": "  SELECT 1;  "})()
        with patch.object(main, "API_KEY", "test-key"), patch.object(
            main, "genai"
        ) as genai:
            genai.Client.return_value.models.generate_content.return_value = response
            self.assertEqual("SELECT 1;", main.ask_gemini("query"))

    def test_empty_model_response_has_friendly_message(self):
        response = type("Response", (), {"text": None})()
        with patch.object(main, "API_KEY", "test-key"), patch.object(
            main, "genai"
        ) as genai:
            genai.Client.return_value.models.generate_content.return_value = response
            self.assertIn("empty response", main.ask_gemini("query"))

    def test_unexpected_api_failure_does_not_expose_exception(self):
        with patch.object(main, "API_KEY", "test-key"), patch.object(
            main.genai, "Client", side_effect=RuntimeError("private detail")
        ):
            result = main.ask_gemini("query")
        self.assertIn("Unexpected error", result)
        self.assertNotIn("private detail", result)

    def test_exit_option_ends_menu(self):
        inputs = iter(["4"])
        with patch("builtins.print") as mock_print:
            main.main(lambda _prompt: next(inputs))
        self.assertTrue(
            any("Goodbye" in str(call) for call in mock_print.call_args_list)
        )

    def test_eof_ends_menu_cleanly(self):
        def eof(_prompt):
            raise EOFError

        with patch("builtins.print") as mock_print:
            main.main(eof)
        self.assertTrue(
            any("Input closed" in str(call) for call in mock_print.call_args_list)
        )


if __name__ == "__main__":
    unittest.main()
