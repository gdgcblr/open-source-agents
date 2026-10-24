from pathlib import Path
import tempfile
import unittest

from first_pr_compass.analyzer import analyze_repository


FIXTURE_REPOSITORY = Path(__file__).parent / "fixtures" / "sample-repo"


class AnalyzeRepositoryTests(unittest.TestCase):
    def test_finds_setup_test_contribution_and_starter_task_evidence(self):
        analysis = analyze_repository(FIXTURE_REPOSITORY)

        self.assertTrue(any("pip install" in item.evidence.text for item in analysis.setup_steps))
        self.assertTrue(
            any(
                item.command == "python -m unittest discover -s tests -v"
                for item in analysis.test_commands
            )
        )
        self.assertTrue(analysis.contribution_guidance)
        self.assertEqual(len(analysis.starter_tasks), 1)
        self.assertEqual(analysis.starter_tasks[0].evidence.path, "src/example.py")
        self.assertEqual(analysis.starter_tasks[0].evidence.line, 2)

    def test_missing_directory_is_reported(self):
        with self.assertRaisesRegex(ValueError, "does not exist"):
            analyze_repository(FIXTURE_REPOSITORY / "missing")

    def test_ignores_generic_setup_mentions_and_template_or_fixture_content(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "README.md").write_text(
                "# Project\n\nSetup is important for contributors.\n"
                "Install with `pip install -e .`.\n",
                encoding="utf-8",
            )
            (root / "template").mkdir()
            (root / "template" / "README.md").write_text(
                "Run `pytest`.\n", encoding="utf-8"
            )
            (root / "tests" / "fixtures").mkdir(parents=True)
            (root / "tests" / "fixtures" / "sample.py").write_text(
                "# TODO: this is only sample content\n", encoding="utf-8"
            )
            (root / "src").mkdir()
            (root / "src" / "app.py").write_text(
                "# TODO: validate user input\n"
                'example = "# TODO: this is a string, not a task"\n',
                encoding="utf-8",
            )
            (root / "src" / "schema.sql").write_text(
                "-- TODO: add a useful index\n", encoding="utf-8"
            )

            analysis = analyze_repository(root)

        self.assertEqual([item.command for item in analysis.setup_steps], ["pip install -e ."])
        self.assertEqual(analysis.test_commands, [])
        self.assertEqual(
            {item.evidence.path for item in analysis.starter_tasks},
            {"src/app.py", "src/schema.sql"},
        )


if __name__ == "__main__":
    unittest.main()
