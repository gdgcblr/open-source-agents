import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from checker import check_project


class TestProjectReadinessChecker(unittest.TestCase):
    def test_all_files_present(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir)
            (project / "README.md").touch()
            (project / "requirements.txt").touch()
            (project / ".gitignore").touch()
            (project / ".env.example").touch()

            output = StringIO()
            with redirect_stdout(output):
                result = check_project(project)

            self.assertEqual(result, 4)
            self.assertIn("4/4 checks passed", output.getvalue())

    def test_missing_files_are_reported(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = StringIO()
            with redirect_stdout(output):
                result = check_project(Path(temp_dir))

            self.assertEqual(result, 0)
            self.assertIn("[MISSING]", output.getvalue())

    def test_invalid_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_path = Path(temp_dir) / "does-not-exist"

            output = StringIO()
            with redirect_stdout(output):
                result = check_project(invalid_path)

            self.assertEqual(result, -1)
            self.assertIn("not a valid directory", output.getvalue())


if __name__ == "__main__":
    unittest.main()