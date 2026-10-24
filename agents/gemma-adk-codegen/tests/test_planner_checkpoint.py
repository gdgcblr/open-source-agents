import json
import unittest
from unittest.mock import AsyncMock, patch

from main import ClarificationRequired, parse_planner_result, request_plan


class PlannerCheckpointTests(unittest.IsolatedAsyncioTestCase):
    def test_parses_targeted_clarification_questions(self):
        response = json.dumps(
            {
                "status": "clarification_required",
                "questions": [
                    {
                        "id": "q1",
                        "question": "Which persistence option should the app use?",
                        "options": ["SQLite", "PostgreSQL"],
                    }
                ],
            }
        )
        parsed = parse_planner_result(response, max_tasks=5)
        self.assertEqual(parsed["status"], "clarification_required")
        self.assertEqual(parsed["questions"][0]["id"], "q1")

    def test_rejects_too_many_clarification_questions(self):
        response = json.dumps(
            {
                "status": "clarification_required",
                "questions": [
                    {"question": f"Question {number}?", "options": []}
                    for number in range(6)
                ],
            }
        )
        with self.assertRaisesRegex(ValueError, "at most 5 questions"):
            parse_planner_result(response, max_tasks=5)

    def test_repairs_missing_json_delimiters_before_schema_validation(self):
        malformed = '''{"status":"clarification_required","questions":[{"id":"q1","question":"What is the shop name?" "options":["Shop A","Shop B"]}]}'''
        parsed = parse_planner_result(malformed, max_tasks=5)
        self.assertEqual(parsed["status"], "clarification_required")
        self.assertEqual(parsed["questions"][0]["question"], "What is the shop name?")

    def test_repairs_trailing_explanation_after_json(self):
        malformed = '''{"status":"clarification_required","questions":[{"id":"q1","question":"Choose a platform?","options":[]}]}\nLet me know your answer.'''
        parsed = parse_planner_result(malformed, max_tasks=5)
        self.assertEqual(parsed["questions"][0]["id"], "q1")

    def test_repaired_json_still_requires_valid_planner_schema(self):
        with self.assertRaisesRegex(ValueError, "Clarification response must contain questions"):
            parse_planner_result('{"status":"clarification_required",}', max_tasks=5)

    async def test_planner_receives_answers_in_followup_request(self):
        clarification = json.dumps(
            {
                "status": "clarification_required",
                "questions": [{"id": "q1", "question": "Target language?", "options": ["Python"]}],
            }
        )
        ready = json.dumps(
            {
                "status": "ready",
                "project_name": "Number Toolkit",
                "tasks": [
                    {
                        "title": "Build Python app",
                        "description": "Build the requested application in Python.",
                        "acceptance_criteria": ["The app starts."],
                    }
                ],
            }
        )
        with patch("main.run_agent", new=AsyncMock(side_effect=[clarification, ready])) as mocked:
            first = await request_plan("Create a todo app", 4)
            second = await request_plan(
                "Create a todo app",
                4,
                [{"q1": "Python"}],
            )

        self.assertEqual(first["status"], "clarification_required")
        self.assertEqual(second["status"], "ready")
        self.assertEqual(second["project_name"], "Number Toolkit")
        second_prompt = mocked.await_args_list[1].args[2]
        self.assertIn('"Python"', second_prompt)

    async def test_generate_task_plan_raises_checkpoint_for_clarifications(self):
        response = json.dumps(
            {
                "status": "clarification_required",
                "questions": [{"id": "q1", "question": "Target platform?", "options": []}],
            }
        )
        with patch("main.run_agent", new=AsyncMock(return_value=response)):
            with self.assertRaises(ClarificationRequired) as captured:
                await __import__("main").generate_task_plan("Build an app", 3)
        self.assertEqual(captured.exception.questions[0]["id"], "q1")

    async def test_force_ready_hint_is_sent_to_planner(self):
        ready = json.dumps(
            {
                "status": "ready",
                "tasks": [
                    {
                        "title": "Build app",
                        "description": "Build using conventional defaults.",
                        "acceptance_criteria": ["App starts."],
                    }
                ],
            }
        )
        with patch("main.run_agent", new=AsyncMock(return_value=ready)) as mocked:
            await request_plan("Build an app", 3, force_ready=True)
        self.assertIn("Do not ask more questions", mocked.await_args.args[2])

    async def test_missing_project_name_uses_description_and_clarification_answers(self):
        ready = json.dumps(
            {
                "status": "ready",
                "tasks": [
                    {
                        "title": "Create app",
                        "description": "Create the application.",
                        "acceptance_criteria": ["App starts."],
                    }
                ],
            }
        )
        with patch("main.run_agent", new=AsyncMock(return_value=ready)):
            result = await request_plan(
                "Build a todo list application",
                3,
                [{"persistence": "SQLite", "features": "due dates and priorities"}],
            )
        self.assertIn("Todo List", result["project_name"])


if __name__ == "__main__":
    unittest.main()