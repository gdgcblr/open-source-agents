"""
Unit tests for pr-reviewer agent tools and diff extraction.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main


class TestPrReviewer(unittest.TestCase):

    def test_get_pr_changed_files(self):
        # Test diff stats against HEAD~1 or staged
        res = main.get_pr_changed_files(base_branch="HEAD~1", staged_only=False)
        self.assertIn("summary", res)
        self.assertIn("Changed Files:", res["summary"])

    def test_read_repo_file_existing(self):
        res = main.read_repo_file("README.md")
        self.assertEqual(res["error"], "")
        self.assertIn("open-source-ai", res["content"])

    def test_read_repo_file_non_existent(self):
        res = main.read_repo_file("this-file-does-not-exist.xyz")
        self.assertIn("does not exist", res["error"])


if __name__ == "__main__":
    unittest.main()
