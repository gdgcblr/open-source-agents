"""Offline tests for the focus coach's storage and deterministic tools."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from typing import get_args, get_type_hints
from unittest.mock import patch

from pydantic import ValidationError

from weekly_focus_coach.models import FocusPlan, FocusState, PlannedAction, WeeklyGoal
from weekly_focus_coach.storage import JsonStore, StorageError
from weekly_focus_coach import tools


class FocusCoachTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_file = Path(self.temp_dir.name) / "focus.json"
        self.env = patch.dict(os.environ, {"FOCUS_DATA_PATH": str(self.data_file), "FOCUS_TIMEZONE": "UTC"})
        self.env.start()
        self.store = JsonStore()
        self.week = "2026-10-19"

    def tearDown(self) -> None:
        self.env.stop()
        self.temp_dir.cleanup()

    def goal(self, title: str, priority: int = 1, **kwargs: object) -> dict[str, object]:
        result = tools.set_weekly_goal(title=title, priority=priority, success_criteria="Finish this week's planned work", metric_type="milestones", milestones="Practice answers;Complete mock interview", week_start=self.week, **kwargs)
        return result["goal"]  # type: ignore[return-value]

    def test_new_store_is_empty_and_does_not_create_a_file(self) -> None:
        state = self.store.load()
        self.assertEqual(state, FocusState())
        self.assertFalse(self.data_file.exists())

    def test_one_or_two_goals_per_week_and_separate_weeks(self) -> None:
        self.goal("Interview prep")
        self.goal("Focused work", priority=2)
        with self.assertRaisesRegex(ValueError, "two goals"):
            self.goal("Reading", priority=2)
        tools.set_weekly_goal("Reading", 1, "Read each day", "minutes", target_minutes=90, week_start="2026-10-26")
        self.assertEqual(len(self.store.load().goals), 3)

    def test_goal_tool_schema_constrains_metric_type_for_the_model(self) -> None:
        metric_type = get_type_hints(tools.set_weekly_goal)["metric_type"]
        self.assertEqual(get_args(metric_type), ("minutes", "milestones"))

    def test_time_spent_does_not_complete_outcome_milestones(self) -> None:
        goal = self.goal("Interview prep")
        tools.log_activity("Studied algorithms", 45, "evening", goal_id=goal["id"], accomplishment="Reviewed arrays")
        metrics = tools.get_weekly_metrics(self.week)["goals"][0]
        self.assertEqual(metrics["time_spent_minutes"], 45)
        self.assertEqual(metrics["progress"]["completed"], 0)

    def test_progress_is_per_goal_and_bar_is_ten_segments(self) -> None:
        one = self.goal("Interview prep")
        two = self.goal("Focused work", 2)
        tools.update_goal_progress(one["id"], one["milestones"][0]["id"], "Practiced out loud")
        metrics = tools.get_weekly_metrics(self.week)["goals"]
        self.assertEqual(metrics[0]["progress"]["percent"], 50)
        self.assertEqual(metrics[0]["progress"]["bar"], "█████░░░░░")
        self.assertEqual(metrics[1]["progress"]["percent"], 0)
        self.assertEqual(two["title"], metrics[1]["title"])

    def test_milestone_update_sets_the_reported_set_and_allows_correction(self) -> None:
        goal = self.goal("Interview prep")
        first, second = [item["id"] for item in goal["milestones"]]
        tools.update_goal_progress(goal["id"], f"{first},{second}", "Finished both milestones")
        tools.update_goal_progress(goal["id"], first, "Corrected the earlier update")
        states = self.store.load().goals[0].milestones
        self.assertEqual([m.completed for m in states], [True, False])
        self.assertEqual(states[0].completion_note, "Corrected the earlier update")
        self.assertEqual(states[1].completion_note, "")

    def test_activity_correction_replaces_duration_instead_of_duplicating(self) -> None:
        activity = tools.log_activity("Reading", 25, "morning", accomplishment="Read 8 pages")
        tools.correct_activity(activity["activity_id"], duration_minutes=35)
        state = self.store.load()
        self.assertEqual(len(state.activities), 1)
        self.assertEqual(state.activities[0].duration_minutes, 35)

    def test_rejects_invalid_week_dates_and_time_targets(self) -> None:
        with self.assertRaises(ValueError):
            tools.set_weekly_goal("Goal", 1, "Criteria", "minutes", target_minutes=-1, week_start=self.week)
        with self.assertRaises(ValidationError):
            WeeklyGoal(title="Bad", week_start=date(2026, 10, 20), priority=1, success_criteria="Done", metric_type="minutes", target_minutes=30)
        with self.assertRaises(ValidationError):
            WeeklyGoal(title="   ", week_start=date(2026, 10, 19), priority=1, success_criteria="Done", metric_type="minutes", target_minutes=30)

    def test_rejects_unknown_goal_and_milestone(self) -> None:
        with self.assertRaisesRegex(ValueError, "Goal not found"):
            tools.update_goal_progress("missing", "x", "Completed something")
        goal = self.goal("Interview prep")
        with self.assertRaisesRegex(ValueError, "Unknown milestone"):
            tools.update_goal_progress(goal["id"], "unknown", "Reported this")

    def test_plan_requires_confirmation_and_fits_available_time(self) -> None:
        goal = self.goal("Interview prep")
        result = tools.save_focus_plan("2026-10-24", goal["id"], "Practice one answer", 30, 30)
        self.assertEqual(result["status"], "needs_confirmation")
        self.assertEqual(len(self.store.load().focus_plans), 0)
        saved = tools.save_focus_plan("2026-10-24", goal["id"], "Practice one answer", 30, 30, approved=True)
        self.assertEqual(saved["status"], "success")
        with self.assertRaises(ValidationError):
            FocusPlan(plan_date=date(2026, 10, 24), available_minutes=20, actions=[PlannedAction(goal_id=goal["id"], description="Practice", duration_minutes=30)], approved=True)

    def test_corrupt_json_is_reported_and_preserved(self) -> None:
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        original = "{not json"
        self.data_file.write_text(original, encoding="utf-8")
        with self.assertRaises(StorageError):
            self.store.load()
        with self.assertRaises(StorageError):
            self.store.update(lambda state: state.goals.clear())
        self.assertEqual(self.data_file.read_text(encoding="utf-8"), original)

    def test_json_round_trip_uses_iso_dates_and_private_file_mode(self) -> None:
        self.goal("Interview prep")
        data = json.loads(self.data_file.read_text(encoding="utf-8"))
        self.assertEqual(data["goals"][0]["week_start"], self.week)
        self.assertEqual(data["revision"], 1)
        self.assertEqual(self.data_file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.store.load().goals[0].week_start.isoformat(), self.week)


if __name__ == "__main__":
    unittest.main()
