
import base64
import unittest
from unittest.mock import Mock, patch

from agents.repo_guide.tools import get_repository_info, parse_github_url


class TestParseGitHubUrl(unittest.TestCase):
    def test_valid_repository_url(self):
        owner, repo = parse_github_url(
            "https://github.com/gdgcblr/open-source-agents"
        )
        self.assertEqual(owner, "gdgcblr")
        self.assertEqual(repo, "open-source-agents")

    def test_repository_url_with_git_suffix(self):
        owner, repo = parse_github_url(
            "https://github.com/gdgcblr/open-source-agents.git"
        )
        self.assertEqual(owner, "gdgcblr")
        self.assertEqual(repo, "open-source-agents")

    def test_invalid_url_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_github_url("https://example.com/not-a-repository")


class TestGetRepositoryInfo(unittest.TestCase):
    @patch("agents.repo_guide.tools.requests.get")
    def test_successful_repository_lookup(self, mock_get):
        metadata_response = Mock()
        metadata_response.status_code = 200
        metadata_response.json.return_value = {
            "full_name": "gdgcblr/open-source-agents",
            "description": "An open-source AI project",
            "language": "Python",
            "stargazers_count": 26,
            "html_url": (
                "https://github.com/gdgcblr/open-source-agents"
            ),
            "default_branch": "main",
        }
        metadata_response.raise_for_status.return_value = None

        readme_text = "# Open Source Agents\n\nWelcome!"
        encoded_readme = base64.b64encode(
            readme_text.encode("utf-8")
        ).decode("ascii")

        readme_response = Mock()
        readme_response.status_code = 200
        readme_response.json.return_value = {
            "content": encoded_readme
        }

        mock_get.side_effect = [
            metadata_response,
            readme_response,
        ]

        result = get_repository_info(
            "https://github.com/gdgcblr/open-source-agents"
        )

        self.assertEqual(
            result["name"], "gdgcblr/open-source-agents"
        )
        self.assertEqual(result["language"], "Python")
        self.assertEqual(result["stars"], 26)
        self.assertIn("Welcome!", result["readme"])
        self.assertNotIn("error", result)

    @patch("agents.repo_guide.tools.requests.get")
    def test_rate_limit_returns_clear_error(self, mock_get):
        response = Mock()
        response.status_code = 403
        response.headers = {
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": "1790000000",
        }
        mock_get.return_value = response

        result = get_repository_info(
            "https://github.com/gdgcblr/open-source-agents"
        )

        self.assertIn("error", result)
        self.assertIn("rate limit", result["error"].lower())
        self.assertEqual(result["remaining_requests"], "0")

    @patch("agents.repo_guide.tools.requests.get")
    def test_missing_repository_returns_clear_error(self, mock_get):
        response = Mock()
        response.status_code = 404
        mock_get.return_value = response

        result = get_repository_info(
            "https://github.com/gdgcblr/does-not-exist"
        )

        self.assertIn("error", result)
        self.assertIn("not found", result["error"].lower())


if __name__ == "__main__":
    unittest.main()
