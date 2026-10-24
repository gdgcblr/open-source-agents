"""
Unit tests for changelog-generator.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main


class TestChangelogGenerator(unittest.TestCase):

    def test_parse_conventional_feat(self):
        commit = {
            "hash": "abc1234",
            "author": "Alice",
            "date": "2026-10-24",
            "subject": "feat(auth): add OAuth2 provider support",
            "body": "",
        }
        res = main.parse_conventional_commit(commit)
        self.assertEqual(res["type"], "feat")
        self.assertEqual(res["scope"], "auth")
        self.assertFalse(res["breaking"])
        self.assertEqual(res["description"], "add OAuth2 provider support")

    def test_parse_breaking_change(self):
        commit = {
            "hash": "def5678",
            "author": "Bob",
            "date": "2026-10-24",
            "subject": "feat(api)!: remove deprecated v1 endpoints",
            "body": "BREAKING CHANGE: v1 API routes are removed.",
        }
        res = main.parse_conventional_commit(commit)
        self.assertTrue(res["breaking"])

    def test_group_commits(self):
        parsed = [
            {"type": "feat", "scope": "core", "breaking": False, "description": "new feature", "hash": "1", "author": "A", "date": "D"},
            {"type": "fix", "scope": "db", "breaking": False, "description": "fix null pointer", "hash": "2", "author": "B", "date": "D"},
            {"type": "feat", "scope": "api", "breaking": True, "description": "break api", "hash": "3", "author": "C", "date": "D"},
        ]
        grouped = main.group_commits(parsed)
        self.assertIn("breaking", grouped)
        self.assertIn("feat", grouped)
        self.assertIn("fix", grouped)

    def test_generate_markdown(self):
        grouped = {
            "feat": [{"scope": "ui", "description": "add dark mode", "hash": "abc"}],
        }
        md = main.generate_markdown("v1.1.0", grouped)
        self.assertIn("## v1.1.0", md)
        self.assertIn("🚀 Features & Enhancements", md)
        self.assertIn("**ui:** add dark mode (`abc`)", md)


if __name__ == "__main__":
    unittest.main()
