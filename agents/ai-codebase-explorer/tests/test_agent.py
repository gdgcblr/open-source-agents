import tempfile
import unittest
from pathlib import Path

from agent import is_sensitive_file, scan_repository, search_code


class CodeExplorerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "auth.py").write_text(
            "def validate_token(token):\n"
            "    if token is None:\n"
            "        return False\n"
            "    return check_signature(token)\n",
            encoding="utf-8",
        )
        (self.root / ".git").mkdir()
        (self.root / ".git" / "hidden.py").write_text(
            "validate_token hidden\n", encoding="utf-8"
        )
        (self.root / ".env").write_text(
            "API_KEY=not-a-real-key\n", encoding="utf-8"
        )
        (self.root / "README.md").write_text(
            "# Authentication\nThe validate_token function checks credentials.\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_search_returns_repo_relative_path_and_line(self):
        results = search_code(self.root, "validate_token")
        self.assertTrue(results)
        self.assertTrue(any(item["path"] == "auth.py" for item in results))
        self.assertTrue(all(item["line"] >= 1 for item in results))

    def test_ignored_directories_are_not_scanned(self):
        resolved_root = self.root.resolve()
        paths = {
            path.relative_to(resolved_root).as_posix()
            for path in scan_repository(self.root)
        }
        self.assertIn("auth.py", paths)
        self.assertNotIn(".git/hidden.py", paths)

    def test_sensitive_files_are_excluded(self):
        paths = {path.name for path in scan_repository(self.root)}
        self.assertNotIn(".env", paths)
        self.assertTrue(is_sensitive_file(Path("service-private_key.pem")))

    def test_empty_query_returns_no_results(self):
        self.assertEqual(search_code(self.root, "??"), [])

    def test_invalid_repository_path_raises(self):
        with self.assertRaises(ValueError):
            search_code(self.root / "does-not-exist", "token")


if __name__ == "__main__":
    unittest.main()
