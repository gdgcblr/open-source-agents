import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import main


TASKS = [
    {
        "id": "task-001",
        "title": "Create entry point",
        "description": "Create application entry point.",
        "acceptance_criteria": ["Entry point exists."],
    },
    {
        "id": "task-002",
        "title": "Add tests",
        "description": "Add application tests.",
        "acceptance_criteria": ["Tests cover core behavior."],
    },
]


class ParallelWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_task_agents_run_in_parallel_then_synthesis_runs(self):
        active: set[tuple[str, str | None]] = set()
        maximum_active = 0
        completed_tasks: set[str] = set()
        calls: list[tuple[str, str | None]] = []
        events: list[dict[str, str | None]] = []
        synthesis_call_count = 0

        async def fake_run_agent(name, instruction, prompt, progress_callback=None, task_id=None):
            nonlocal maximum_active, synthesis_call_count
            key = (name, task_id)
            calls.append(key)
            if progress_callback:
                progress_callback({"agent": name, "status": "running", "task_id": task_id})
            active.add(key)
            maximum_active = max(maximum_active, len(active))
            await asyncio.sleep(0.01)
            active.remove(key)
            if name == "coding_agent":
                result = json.dumps({"files": [{"path": f"{task_id}.py", "content": "value = 1\n"}]})
            elif name == "review_agent":
                result = "Review complete."
            elif name == "testing_agent":
                result = "Test plan complete."
            elif name == "synthesis_agent":
                self.assertEqual(completed_tasks, {"task-001", "task-002"})
                synthesis_call_count += 1
                result = "{files: malformed}" if synthesis_call_count == 1 else "{}"
            elif name == "synthesis_repair_agent":
                result = json.dumps({"files": [{"path": "app.py", "content": "value = 1\n"}]})
            else:
                raise AssertionError(f"Unexpected agent: {name}")
            if progress_callback:
                progress_callback({"agent": name, "status": "completed", "task_id": task_id})
            return result

        def progress_callback(event):
            events.append(event)
            if event["agent"] in {"review_agent", "testing_agent"} and event["status"] == "completed":
                if event["agent"] == "testing_agent":
                    completed_tasks.add(event["task_id"])

        with tempfile.TemporaryDirectory() as temporary_directory:
            with (
                patch.object(main, "generate_task_plan", new=AsyncMock(return_value=TASKS)),
                patch.object(main, "run_agent", new=AsyncMock(side_effect=fake_run_agent)),
            ):
                run_dir = await main.run_workflow(
                    "Create a small application",
                    Path(temporary_directory),
                    max_tasks=2,
                    progress_callback=progress_callback,
                    max_parallel_tasks=2,
                    project_name="Sample Application",
                )

            self.assertGreaterEqual(maximum_active, 3)
            self.assertTrue(run_dir.name.startswith("sample-application-"))
            plan = json.loads((run_dir / "task-plan.json").read_text())
            self.assertEqual(plan["project_name"], "Sample Application")
            self.assertEqual((run_dir / "project" / "app.py").read_text(), "value = 1\n")
            self.assertTrue((run_dir / "task-001-create-entry-point" / "review.md").is_file())
            self.assertEqual(
                json.loads((run_dir / "final-files.json").read_text()),
                ["app.py", "README.md"],
            )

        self.assertEqual(sum(name == "synthesis_agent" for name, _ in calls), 1)
        self.assertEqual(sum(name == "synthesis_repair_agent" for name, _ in calls), 1)
        self.assertTrue(any(event["agent"] == "synthesis_agent" and event["status"] == "running" for event in events))

    async def test_repairs_malformed_coder_manifest_once(self):
        valid_manifest = json.dumps({"files": [{"path": "src/app.py", "content": "print('ok')\n"}]})
        with patch(
            "main.run_agent",
            new=AsyncMock(side_effect=["{files: invalid}", valid_manifest]),
        ) as mocked_run_agent:
            files = await main.generate_task_files("Build app", TASKS[0], None)

        self.assertEqual(files[0]["path"], "src/app.py")
        self.assertEqual(mocked_run_agent.await_count, 2)
        self.assertEqual(mocked_run_agent.await_args_list[1].args[0], "coding_repair_agent")

    async def test_rejects_coder_output_after_one_failed_repair(self):
        with patch(
            "main.run_agent",
            new=AsyncMock(side_effect=["invalid", "still invalid"]),
        ) as mocked_run_agent:
            with self.assertRaisesRegex(ValueError, "after one JSON repair"):
                await main.generate_task_files("Build app", TASKS[0], None)

        self.assertEqual(mocked_run_agent.await_count, 2)

    async def test_uses_validated_proposals_when_synthesis_and_repair_fail(self):
        completed_tasks: set[str] = set()

        async def fake_run_agent(name, instruction, prompt, progress_callback=None, task_id=None):
            if name == "review_agent":
                return "Review available."
            if name == "testing_agent":
                completed_tasks.add(task_id)
                return "Test plan available."
            if name == "synthesis_agent":
                self.assertEqual(completed_tasks, {"task-001"})
                raise RuntimeError("Gemma returned no synthesis response")
            if name == "synthesis_repair_agent":
                raise RuntimeError("Gemma repair returned no JSON")
            raise AssertionError(f"Unexpected run_agent call: {name}")

        progress_events = []
        with tempfile.TemporaryDirectory() as temporary_directory:
            with (
                patch.object(main, "generate_task_plan", new=AsyncMock(return_value=TASKS[:1])),
                patch.object(
                    main,
                    "generate_task_files",
                    new=AsyncMock(
                        return_value=[
                            {"path": "src/app.py", "content": "print('proposal')\n"},
                            {"path": "tests/test_app.py", "content": "def test_app(): pass\n"},
                        ]
                    ),
                ),
                patch.object(main, "run_agent", new=AsyncMock(side_effect=fake_run_agent)),
            ):
                run_dir = await main.run_workflow(
                    "Create app",
                    Path(temporary_directory),
                    max_tasks=1,
                    progress_callback=progress_events.append,
                    project_name="Sample App",
                )

            self.assertEqual(
                (run_dir / "project/src/app.py").read_text(), "print('proposal')\n"
            )
            report = (run_dir / "synthesis.md").read_text()
            self.assertIn("proposal_merge_fallback", report)
            self.assertIn("Gemma returned no synthesis response", report)
            self.assertEqual((run_dir / "final-files.json").exists(), True)
            readme = (run_dir / "project/README.md").read_text()
            self.assertIn("## Setup", readme)
            self.assertIn("## Run", readme)
            self.assertIn("## Tests", readme)
            static_report = (run_dir / "static-checks.md").read_text()
            self.assertIn("Static syntax checks only", static_report)

        self.assertTrue(
            any(event["agent"] == "synthesis_agent" and event["status"] == "fallback_completed"
                for event in progress_events)
        )


class GeneratedProjectValidationTests(unittest.TestCase):
    def test_ensures_readme_contains_runnable_setup_sections(self):
        files = [
            {"path": "requirements.txt", "content": "pytest\n"},
            {"path": "main.py", "content": "print('hi')\n"},
        ]
        completed = main.ensure_project_readme(
            files,
            "Sample Project",
            "Create a small Python program",
            [{"language": "Python"}],
        )
        readme = next(file_entry["content"] for file_entry in completed if file_entry["path"] == "README.md")
        self.assertIn("python -m pip install -r requirements.txt", readme)
        self.assertIn("python main.py", readme)
        self.assertIn("python -m pytest", readme)
        self.assertIn("language: Python", readme)

    def test_static_checks_report_syntax_without_execution(self):
        findings = main.static_check_generated_files(
            [
                {"path": "src/good.py", "content": "value = 1\n"},
                {"path": "src/bad.py", "content": "def broken(:\n pass\n"},
                {"path": "config.json", "content": "{\"ok\": true}"},
            ]
        )
        self.assertEqual(len(findings), 1)
        self.assertIn("src/bad.py", findings[0])

    def test_proposal_merge_preserves_conflicting_files(self):
        results = [
            {
                "task": {"id": "task-001", "title": "One"},
                "implementation_files": [
                    {"path": "inventory_management.py", "content": "version = 1\n"}
                ],
            },
            {
                "task": {"id": "task-002", "title": "Two"},
                "implementation_files": [
                    {"path": "inventory_management.py", "content": "version = 2\n"}
                ],
            },
        ]

        files, conflicts = main.merge_task_proposals(results)
        contents = {item["path"]: item["content"] for item in files}

        self.assertEqual(contents["inventory_management.py"], "version = 1\n")
        self.assertEqual(
            contents["task-proposals/task-002/inventory_management.py"],
            "version = 2\n",
        )
        self.assertEqual(conflicts[0]["task_id"], "task-002")


if __name__ == "__main__":
    unittest.main()