import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.ollama_client import OllamaUnavailable
from security.guardrails import UnsafeAIOutput


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


class LabLensAppTests(unittest.TestCase):
    def create_app(self):
        return AppTest.from_file(str(APP_PATH), default_timeout=10).run()

    def submit_result(self, app):
        app.number_input[0].set_value(5.0).run()
        app.button[0].click().run()

    def test_result_is_not_rendered_before_valid_assessment(self):
        app = self.create_app()

        self.assertIsNone(app.number_input[0].value)
        self.assertNotIn("Your comparison", [item.value for item in app.subheader])
        self.assertIsNone(app.session_state.get("last_assessment"))

    def test_result_remains_visible_and_is_invalidated_when_input_changes(self):
        app = self.create_app()
        self.submit_result(app)

        self.assertEqual(app.session_state["last_assessment"]["status"], "Within supplied range")
        self.assertIn("Your comparison", [item.value for item in app.subheader])

        app.number_input[0].set_value(6.0).run()

        self.assertIsNone(app.session_state.get("last_assessment"))
        self.assertNotIn("Your comparison", [item.value for item in app.subheader])

    def test_changing_test_resets_example_interval_and_clears_result(self):
        app = self.create_app()
        self.submit_result(app)

        app.selectbox[0].set_value("TSH").run()

        self.assertIsNone(app.session_state.get("last_assessment"))
        self.assertIsNone(app.number_input[0].value)
        self.assertEqual(app.session_state["lower"], 0.4)
        self.assertEqual(app.session_state["upper"], 4.0)
        self.assertNotIn("Your comparison", [item.value for item in app.subheader])

    def test_validation_error_is_shown_for_invalid_interval(self):
        app = self.create_app()
        app.number_input[0].set_value(5.0)
        app.number_input[1].set_value(10.0)
        app.number_input[2].set_value(2.0).run()
        app.button[0].click().run()

        self.assertTrue(any("lower limit" in item.value.lower() for item in app.error))
        self.assertIsNone(app.session_state.get("last_assessment"))

    def test_ai_success_survives_rerun_without_duplicate_results(self):
        with patch(
            "application.orchestrator.generate_explanation",
            return_value="This value is within the interval you entered.",
        ) as generate:
            app = self.create_app()
            self.submit_result(app)
            app.button[1].click().run()

        generate.assert_called_once()
        self.assertEqual(
            app.session_state["ai_response"],
            "This value is within the interval you entered.",
        )
        self.assertEqual(
            [item.value for item in app.subheader].count("Your comparison"),
            1,
        )
        self.assertTrue(
            any(
                "This value is within the interval you entered." in item.value
                for item in app.markdown
            )
        )

    def test_ai_failure_preserves_deterministic_result(self):
        with patch(
            "application.orchestrator.generate_explanation",
            side_effect=OllamaUnavailable("Ollama is unavailable."),
        ):
            app = self.create_app()
            self.submit_result(app)
            app.button[1].click().run()

        self.assertIn("Ollama is unavailable.", app.session_state["ai_error"])
        self.assertIsNotNone(app.session_state["last_assessment"])
        self.assertIn("Your comparison", [item.value for item in app.subheader])
        self.assertTrue(any("still here" in item.value for item in app.error))

    def test_blocked_ai_output_preserves_deterministic_result(self):
        with patch(
            "application.orchestrator.generate_explanation",
            side_effect=UnsafeAIOutput("Blocked unsafe response."),
        ):
            app = self.create_app()
            self.submit_result(app)
            app.button[1].click().run()

        self.assertEqual(app.session_state["ai_error"], "blocked")
        self.assertIsNotNone(app.session_state["last_assessment"])
        self.assertIn("Your comparison", [item.value for item in app.subheader])
        self.assertTrue(any("safety checks" in item.value for item in app.error))


if __name__ == "__main__":
    unittest.main()
