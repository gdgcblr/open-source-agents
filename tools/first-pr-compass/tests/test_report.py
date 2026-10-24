import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from first_pr_compass.analyzer import analyze_repository
from first_pr_compass.report import render_json, render_markdown


FIXTURE_REPOSITORY = Path(__file__).parent / "fixtures" / "sample-repo"


class ReportTests(unittest.TestCase):
    def test_markdown_includes_clickable_evidence_and_cautious_empty_states(self):
        report = render_markdown(analyze_repository(FIXTURE_REPOSITORY))

        self.assertIn("[src/example.py:2](src/example.py#L2)", report)
        self.assertIn("python -m unittest discover -s tests -v", report)
        self.assertIn("Suggestions are evidence-based leads", report)

    def test_json_report_has_structured_evidence(self):
        payload = json.loads(render_json(analyze_repository(FIXTURE_REPOSITORY)))

        self.assertEqual(payload["starter_tasks"][0]["evidence"]["path"], "src/example.py")
        self.assertEqual(payload["starter_tasks"][0]["evidence"]["line"], 2)

    def test_markdown_links_github_evidence_to_the_analyzed_ref(self):
        analysis = replace(
            analyze_repository(FIXTURE_REPOSITORY),
            source_url="https://github.com/example/project",
            source_ref="feature/docs",
        )

        report = render_markdown(analysis)

        self.assertIn(
            "https://github.com/example/project/blob/feature/docs/src/example.py#L2",
            report,
        )

    def test_sensitive_environment_files_are_not_scanned(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "README.md").write_text("# Empty project\n", encoding="utf-8")
            (root / ".env").write_text("TODO: do not read this\n", encoding="utf-8")

            analysis = analyze_repository(root)

        self.assertEqual(analysis.starter_tasks, [])


if __name__ == "__main__":
    unittest.main()
