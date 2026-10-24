import json
import unittest
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

import github_api


class GitHubAPITests(unittest.TestCase):
    def test_parse_public_issue_url(self):
        self.assertEqual(
            github_api.parse_issue_url("https://github.com/pallets/flask/issues/123?source=share"),
            ("pallets", "flask", 123),
        )

    def test_rejects_non_github_or_pull_request_urls(self):
        for url in (
            "http://github.com/pallets/flask/issues/1",
            "https://example.com/pallets/flask/issues/1",
            "https://github.com/pallets/flask/pull/1",
        ):
            with self.subTest(url=url), self.assertRaises(github_api.GitHubAPIError):
                github_api.parse_issue_url(url)

    @patch("github_api.urlopen")
    def test_fetch_public_issue(self, mock_urlopen):
        issue = {
            "title": "Export crashes",
            "body": "Clicking export closes the app.",
            "state": "open",
            "html_url": "https://github.com/example/project/issues/7",
        }
        mock_urlopen.return_value.__enter__.return_value = BytesIO(json.dumps(issue).encode())
        actual = github_api.fetch_public_issue("https://github.com/example/project/issues/7")
        self.assertEqual(actual["title"], "Export crashes")
        self.assertEqual(actual["body"], "Clicking export closes the app.")
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.github.com/repos/example/project/issues/7")
        self.assertEqual(request.get_header("User-agent"), "issue-triage-assistant")

    @patch("github_api.urlopen")
    def test_rejects_pull_request_response(self, mock_urlopen):
        data = {"title": "A pull request", "body": "", "pull_request": {"url": "https://api.github.com"}}
        mock_urlopen.return_value.__enter__.return_value = BytesIO(json.dumps(data).encode())
        with self.assertRaisesRegex(github_api.GitHubAPIError, "pull request"):
            github_api.fetch_public_issue("https://github.com/example/project/issues/7")

    @patch("github_api.urlopen")
    def test_fetch_repository_labels(self, mock_urlopen):
        data = [{"name": "bug"}, {"name": "good first issue"}, {"description": "no name"}]
        mock_urlopen.return_value.__enter__.return_value = BytesIO(json.dumps(data).encode())
        self.assertEqual(
            github_api.fetch_repository_labels("example", "project"),
            ["bug", "good first issue"],
        )

    @patch("github_api.urlopen", side_effect=HTTPError("", 404, "missing", {}, None))
    def test_not_found_has_actionable_message(self, _mock_urlopen):
        with self.assertRaisesRegex(github_api.GitHubAPIError, "not found"):
            github_api.fetch_public_issue("https://github.com/example/project/issues/7")


if __name__ == "__main__":
    unittest.main()
