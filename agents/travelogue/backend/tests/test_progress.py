import unittest
from backend.progress import STAGES, mark_stage, finish_run


class ProgressTests(unittest.TestCase):
    def run_record(self):
        return {"status": "queued", "stage": "queued", "stages": [],
                "stage_states": {name: "pending" for name in STAGES}}

    def test_parallel_research_reports_both_running_independently(self):
        run = self.run_record()
        mark_stage(run, "destination_researcher")
        mark_stage(run, "season_researcher")
        self.assertEqual(run["stage_states"]["destination_researcher"], "running")
        self.assertEqual(run["stage_states"]["season_researcher"], "running")
        mark_stage(run, "destination_researcher", "completed")
        self.assertEqual(run["stage_states"]["destination_researcher"], "completed")
        self.assertEqual(run["stage_states"]["season_researcher"], "running")

    def test_timeout_marks_only_active_steps_failed(self):
        run = self.run_record()
        mark_stage(run, "destination_researcher")
        mark_stage(run, "destination_researcher", "completed")
        mark_stage(run, "season_researcher")
        finish_run(run, "failed", "Timed out")
        self.assertEqual(run["stage_states"]["destination_researcher"], "completed")
        self.assertEqual(run["stage_states"]["season_researcher"], "failed")
        self.assertEqual(run["stage_states"]["itinerary_planner"], "pending")
        self.assertIn("finished_at", run)

    def test_completion_is_not_invented_and_cannot_regress(self):
        run = self.run_record()
        mark_stage(run, "destination_researcher", "completed")
        mark_stage(run, "destination_researcher")
        finish_run(run, "completed")
        self.assertEqual(run["stage_states"]["destination_researcher"], "completed")
        self.assertEqual(run["stage_states"]["validation"], "pending")
        self.assertEqual(run["stages"], ["destination_researcher"])

    def test_unknown_stage_is_rejected(self):
        with self.assertRaises(ValueError):
            mark_stage(self.run_record(), "book_flights")
