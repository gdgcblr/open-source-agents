
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_guide import create_onboarding_guide
from main import inspect_repository


class RepoReadyTests(unittest.TestCase):
    def test_detects_project_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            (root / "README.md").write_text(
                "# Demo project", encoding="utf-8"
            )
            (root / ".gitignore").write_text(
                ".venv/", encoding="utf-8"
            )
            (root / "requirements.txt").write_text(
                "", encoding="utf-8"
            )
            (root / "tests").mkdir()

            report = inspect_repository(root)

            self.assertEqual(report["passed"], 4)

            documentation = next(
                item for item in report["results"]
                if item["check"] == "Documentation"
            )
            self.assertEqual(documentation["status"], "PASS")

    def test_warns_when_manifest_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            report = inspect_repository(root)

            dependency_check = next(
                item for item in report["results"]
                if item["check"] == "Dependencies"
            )

            self.assertEqual(dependency_check["status"], "WARN")

    def test_ai_guide_falls_back_without_api_key(self):
        # Resolve the actual project directory from this test file.
        root = Path(__file__).resolve().parents[1]

        self.assertTrue(
            root.is_dir(),
            f"Project directory does not exist: {root}",
        )

        with patch.dict("os.environ", {}, clear=True):
            guide = create_onboarding_guide(root)

        self.assertIn("AI mode is unavailable", guide)
        self.assertIn("Local repository checks", guide)

    def test_rejects_missing_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing_path = Path(tmp) / "does-not-exist"

            with self.assertRaises(FileNotFoundError):
                inspect_repository(missing_path)


if __name__ == "__main__":
    unittest.main()
