import unittest
from unittest.mock import AsyncMock, patch

from main import generate_task_plan


VALID_PLAN = (
    '{"tasks":[{"title":"Create app","description":"Build the app",'
    '"acceptance_criteria":["App starts"]}]}'
)


class PlannerRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_repairs_malformed_planner_json_once(self):
        with patch(
            "main.run_agent",
            new=AsyncMock(side_effect=["{tasks: []}", VALID_PLAN]),
        ) as mocked_run_agent:
            tasks = await generate_task_plan("Create an app", max_tasks=3)

        self.assertEqual(tasks[0]["title"], "Create app")
        self.assertEqual(mocked_run_agent.await_count, 2)
        repair_prompt = mocked_run_agent.await_args_list[1].args[2]
        self.assertIn("Repair the previous planner response", repair_prompt)

    async def test_rejects_plan_if_repair_is_still_invalid(self):
        with patch(
            "main.run_agent",
            new=AsyncMock(side_effect=["not json", "still not json"]),
        ) as mocked_run_agent:
            with self.assertRaisesRegex(ValueError, "after one format-repair attempt"):
                await generate_task_plan("Create an app", max_tasks=3)

        self.assertEqual(mocked_run_agent.await_count, 2)


if __name__ == "__main__":
    unittest.main()