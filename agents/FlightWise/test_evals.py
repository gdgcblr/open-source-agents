import json
from pathlib import Path
import unittest

from google.adk.evaluation.eval_config import EvalConfig
from google.adk.evaluation.eval_metrics import EvalMetric
from google.adk.evaluation.eval_set import EvalSet
from google.adk.evaluation.trajectory_evaluator import TrajectoryEvaluator
from google.adk.evaluation.eval_metrics import ToolTrajectoryCriterion
from google.adk.evaluation.eval_case import Invocation
from google.genai import types


EVALS_DIR = Path(__file__).parent / "evals"


class FlightwiseEvalAssetsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eval_set = EvalSet.model_validate_json(
            (EVALS_DIR / "flightwise.evalset.json").read_text()
        )
        cls.config = EvalConfig.model_validate_json(
            (EVALS_DIR / "eval_config.json").read_text()
        )

    def test_eval_set_covers_requirement_gathering_and_searches(self):
        cases = {case.eval_id: case for case in self.eval_set.eval_cases}

        self.assertEqual(
            set(cases),
            {
                "asks_for_missing_requirements",
                "searches_complete_one_way_request",
                "searches_complete_round_trip_request",
            },
        )
        self.assertEqual(cases["asks_for_missing_requirements"].conversation[0].intermediate_data.tool_uses, [])
        for eval_id in (
            "searches_complete_one_way_request",
            "searches_complete_round_trip_request",
        ):
            calls = cases[eval_id].conversation[0].intermediate_data.tool_uses
            self.assertEqual([call.name for call in calls], ["search_flights"])

    def test_eval_config_requires_correct_tool_trajectory(self):
        criterion = ToolTrajectoryCriterion.model_validate(
            self.config.criteria["tool_trajectory_avg_score"].model_dump()
        )
        expected = Invocation(
            user_content=types.Content(role="user", parts=[types.Part(text="test")]),
            intermediate_data={"tool_uses": [{"name": "search_flights", "args": {}}]},
        )
        actual = Invocation(
            user_content=expected.user_content,
            intermediate_data={"tool_uses": [{"name": "search_flights", "args": {"origin": "BLR"}}]},
        )
        result = TrajectoryEvaluator(
            eval_metric=EvalMetric(
                metric_name="tool_trajectory_avg_score",
                criterion=criterion,
            )
        ).evaluate_invocations([actual], [expected])

        self.assertEqual(result.overall_score, 1.0)

    def test_eval_config_includes_response_rubric_metric(self):
        self.assertIn(
            "rubric_based_final_response_quality_v1",
            self.config.criteria,
        )
        for case in self.eval_set.eval_cases:
            self.assertTrue(case.conversation[0].rubrics)

if __name__ == "__main__":
    unittest.main()
