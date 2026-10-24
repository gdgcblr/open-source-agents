import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from first_pr_compass.github import (
    _GitHubRedirectHandler,
    _safe_extract,
    download_github_repository,
    parse_github_url,
)


def make_archive(entries: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return output.getvalue()


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = io.BytesIO(content)
        self.headers: dict[str, str] = {}

    def read(self, size: int = -1) -> bytes:
        return self.content.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.content.close()


class FakeOpener:
    def __init__(self, content: bytes):
        self.response = FakeResponse(content)

    def open(self, _request, timeout: int):
        if timeout <= 0:
            raise AssertionError("Expected a positive network timeout")
        return self.response


class GitHubRepositoryTests(unittest.TestCase):
    def test_accepts_public_repository_and_git_suffix(self):
        repository = parse_github_url("https://github.com/Example/project.git")

        self.assertEqual(repository.owner, "Example")
        self.assertEqual(repository.name, "project")
        self.assertEqual(repository.url, "https://github.com/Example/project")

    def test_rejects_non_github_urls_and_non_repository_pages(self):
        for url in (
            "http://github.com/owner/repo",
            "https://github.com/owner/repo/tree/main",
            "https://github.com.evil.example/owner/repo",
            "https://user@github.com/owner/repo",
            "https://github.com/owner/repo?download=true",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                parse_github_url(url)

    def test_fetches_public_archive_and_cleans_temporary_checkout(self):
        metadata = json.dumps({"default_branch": "main"}).encode("utf-8")
        archive = make_archive(
            {
                "Example-project-main/README.md": "# Example\n",
                "Example-project-main/src/main.rs": "// TODO: improve parsing\n",
            }
        )
        openers = [FakeOpener(metadata), FakeOpener(archive)]

        with patch(
            "first_pr_compass.github.urllib.request.build_opener",
            side_effect=openers,
        ):
            with download_github_repository("https://github.com/Example/project") as repo:
                checkout = repo.path
                self.assertEqual(repo.url, "https://github.com/Example/project")
                self.assertEqual(repo.ref, "main")
                self.assertEqual(
                    (repo.path / "src" / "main.rs").read_text(encoding="utf-8"),
                    "// TODO: improve parsing\n",
                )
            self.assertFalse(checkout.exists())

    def test_rejects_archive_path_traversal(self):
        archive = make_archive({"repo-root/../../outside.txt": "unsafe"})

        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(ValueError, "unsafe file path"):
                _safe_extract(archive, Path(temporary_directory))

    def test_rejects_invalid_ref_before_downloading_archive(self):
        metadata = json.dumps({"default_branch": "main"}).encode("utf-8")

        with patch(
            "first_pr_compass.github.urllib.request.build_opener",
            return_value=FakeOpener(metadata),
        ):
            with self.assertRaisesRegex(ValueError, "Invalid GitHub ref"):
                with download_github_repository(
                    "https://github.com/Example/project", "../private"
                ):
                    self.fail("Invalid refs must fail before extraction.")

    def test_rejects_redirects_outside_github_hosts(self):
        handler = _GitHubRedirectHandler()

        with self.assertRaisesRegex(ValueError, "unsafe archive redirect"):
            handler.redirect_request(
                None,
                None,
                302,
                "Found",
                {},
                "https://example.invalid/archive.zip",
            )


if __name__ == "__main__":
    unittest.main()
