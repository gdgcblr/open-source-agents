"""
Unit and integration tests for git-commit-agent.
"""

import os
import re
import sys
import unittest

# Add parent directory to path so main can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main


class TestGitCommitAgent(unittest.TestCase):

    def test_extract_issue_from_branch(self):
        cases = [
            ("feat/issue-123-login", "#123"),
            ("fix/issue-45", "#45"),
            ("fix/GH-99", "GH-99"),
            ("PROJ-1024-database-migration", "PROJ-1024"),
            ("feature/JIRA-42", "JIRA-42"),
            ("fix/99-fix-broken-links", "#99"),
            ("main", None),
            ("feat/new-ui", None),
        ]
        for branch, expected in cases:
            with self.subTest(branch=branch):
                self.assertEqual(main.extract_issue_from_branch(branch), expected)

    def test_clean_commit_message(self):
        fenced = "```markdown\nfeat(core): implement caching layer\n```"
        self.assertEqual(main.clean_commit_message(fenced), "feat(core): implement caching layer")

        fenced_simple = "```\nfix(auth): fix token validation\n```"
        self.assertEqual(main.clean_commit_message(fenced_simple), "fix(auth): fix token validation")

        plain = "docs: update API documentation"
        self.assertEqual(main.clean_commit_message(plain), "docs: update API documentation")

    def test_format_message_box(self):
        box = main.format_message_box("feat(cli): add tests")
        self.assertIn("feat(cli): add tests", box)
        self.assertIn("=" * 64, box)

    def test_is_git_repository(self):
        # Current workspace is a git repository
        self.assertTrue(main.is_git_repository())

    def test_conventional_commit_syntax(self):
        conv_regex = r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(?:\([a-zA-Z0-9_\-\./]+\))?!?: [^\n\r]+(?:\n\n.*)?$"
        valid_examples = [
            "feat: add user authentication",
            "fix(api): handle null payload gracefully",
            "chore(deps)!: bump dependencies to latest",
            "docs(readme): fix typo in quickstart guide\n\nDetailed body explanation goes here.",
        ]
        for msg in valid_examples:
            with self.subTest(msg=msg):
                self.assertIsNotNone(re.match(conv_regex, msg, re.DOTALL))


if __name__ == "__main__":
    unittest.main()
