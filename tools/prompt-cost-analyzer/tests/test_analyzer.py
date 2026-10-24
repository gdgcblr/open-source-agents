import unittest
from unittest.mock import patch

from prompt_cost_analyzer.analyzer import _count_tokens, analyze_prompt_cost
from prompt_cost_analyzer.pricing import resolve_rates


class AnalyzePromptCostTests(unittest.TestCase):
    def test_counts_prompt_and_tool_results_and_applies_output_cap(self) -> None:
        with patch(
            "prompt_cost_analyzer.analyzer._count_tokens",
            side_effect=lambda text: len(text.split()),
        ):
            result = analyze_prompt_cost(
                prompt="Summarize this.",
                tool_results=["A tool found three files."],
                model="claude-sonnet-4-6",
                max_output_tokens=1000,
            )

        self.assertEqual(result["prompt_tokens"], 2)
        self.assertEqual(result["tool_result_tokens"], 5)
        self.assertEqual(
            result["estimated_input_tokens"],
            result["prompt_tokens"] + result["tool_result_tokens"],
        )
        self.assertEqual(result["max_output_tokens"], 1000)
        self.assertAlmostEqual(
            result["maximum_estimated_cost_usd"],
            result["estimated_input_cost_usd"] + result["max_output_cost_usd"],
        )

    def test_unknown_model_requires_both_custom_rates(self) -> None:
        with self.assertRaisesRegex(ValueError, "provide both"):
            resolve_rates("my-private-model", input_override=1.0)

    def test_custom_rates_can_price_an_unknown_model(self) -> None:
        with patch("prompt_cost_analyzer.analyzer._count_tokens", return_value=1):
            result = analyze_prompt_cost(
                prompt="Hi",
                tool_results=[],
                model="my-private-model",
                max_output_tokens=20,
                input_usd_per_million=2.0,
                output_usd_per_million=8.0,
            )

        self.assertEqual(result["pricing_source"], "user-supplied")
        self.assertEqual(result["input_usd_per_million"], 2.0)
        self.assertEqual(result["output_usd_per_million"], 8.0)

    def test_partial_override_keeps_other_builtin_rate(self) -> None:
        input_rate, output_rate, _, _ = resolve_rates(
            "claude-sonnet-4-6", input_override=4.0
        )

        self.assertEqual(input_rate, 4.0)
        self.assertEqual(output_rate, 15.0)

    def test_rejects_negative_output_cap_and_invalid_rate(self) -> None:
        with self.assertRaisesRegex(ValueError, "zero or greater"):
            analyze_prompt_cost("Hi", [], "claude-sonnet-4-6", -1)
        with self.assertRaisesRegex(ValueError, "finite, non-negative"):
            analyze_prompt_cost(
                "Hi",
                [],
                "claude-sonnet-4-6",
                10,
                input_usd_per_million=float("nan"),
            )

    def test_tokenizer_counts_without_treating_special_tokens_as_controls(self) -> None:
        fake_encoding = unittest.mock.Mock()
        fake_encoding.encode.return_value = [1, 2, 3]
        with patch(
            "prompt_cost_analyzer.analyzer._get_encoding",
            return_value=fake_encoding,
        ):
            self.assertEqual(_count_tokens("<|im_start|>hello"), 3)

        fake_encoding.encode.assert_called_once_with(
            "<|im_start|>hello", disallowed_special=()
        )


if __name__ == "__main__":
    unittest.main()
