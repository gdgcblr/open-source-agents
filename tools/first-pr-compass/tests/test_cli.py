from contextlib import contextmanager
from io import StringIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from first_pr_compass.cli import guide_me_to_contribute, main
from first_pr_compass.github import DownloadedRepository


FIXTURE_REPOSITORY = Path(__file__).parent / "fixtures" / "sample-repo"


class CliTests(unittest.TestCase):
    def test_guide_alias_prints_a_local_report(self):
        stdout = StringIO()
        with patch.object(sys, "argv", ["guide-me-to-contribute", str(FIXTURE_REPOSITORY)]):
            with patch("sys.stdout", stdout):
                result = guide_me_to_contribute()

        self.assertEqual(result, 0)
        self.assertIn("Starter task candidates", stdout.getvalue())

    def test_github_input_uses_temporary_source_and_remote_evidence_links(self):
        stdout = StringIO()

        @contextmanager
        def fake_download(repository_url, ref):
            self.assertEqual(repository_url, "https://github.com/example/project")
            self.assertEqual(ref, "feature/docs")
            yield DownloadedRepository(
                path=FIXTURE_REPOSITORY,
                url="https://github.com/example/project",
                ref="feature/docs",
            )

        with patch(
            "first_pr_compass.cli.download_github_repository", fake_download
        ):
            with patch("sys.stdout", stdout):
                result = main(
                    [
                        "https://github.com/example/project",
                        "--ref",
                        "feature/docs",
                        "--output",
                        "-",
                    ]
                )

        self.assertEqual(result, 0)
        self.assertIn(
            "https://github.com/example/project/blob/feature/docs/src/example.py#L2",
            stdout.getvalue(),
        )

    def test_ref_is_rejected_for_local_paths(self):
        stderr = StringIO()
        with patch("sys.stderr", stderr):
            result = main([str(FIXTURE_REPOSITORY), "--ref", "main", "--output", "-"])

        self.assertEqual(result, 2)
        self.assertIn("--ref can only be used", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
