import unittest

from progress_ui import render_agent_tree_html


class AgentTreeTests(unittest.TestCase):
    def test_highlights_active_agents_and_marks_completed_agents(self):
        tasks = [{"id": "task-001", "title": "Create API"}]
        progress = {
            "problem_planner": {"status": "completed"},
            "task-001:coding_agent": {"status": "completed"},
            "task-001:review_agent": {"status": "running"},
            "task-001:testing_agent": {"status": "running"},
        }

        rendered = render_agent_tree_html(progress, tasks, "task-001")

        self.assertIn("Problem planner</span><span class='agent-state state-completed'>DONE", rendered)
        self.assertEqual(rendered.count("class='agent-tree-row level-2 active'"), 2)
        self.assertIn("Coding agent</span><span class='agent-state state-completed'>DONE", rendered)
        self.assertIn("Current task task-001: Create API", rendered)

    def test_escapes_untrusted_task_title(self):
        rendered = render_agent_tree_html(
            {"problem_planner": {"status": "completed"}},
            [{"id": "task-001", "title": "<script>alert(1)</script>"}],
        )

        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_shows_repair_agent_when_repair_was_needed(self):
        rendered = render_agent_tree_html(
            {
                "problem_planner": {"status": "completed"},
                "problem_planner_repair": {"status": "completed"},
            }
        )
        self.assertIn("Planner format recovery", rendered)
        self.assertIn('state-completed\'>DONE', rendered)

    def test_shows_synthesis_as_final_stage(self):
        rendered = render_agent_tree_html(
            {"synthesis_agent": {"status": "running"}},
            [{"id": "task-001", "title": "Create app"}],
        )
        self.assertIn("Final project synthesis", rendered)
        self.assertIn("level-1 active", rendered)


if __name__ == "__main__":
    unittest.main()