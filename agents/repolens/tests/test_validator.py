"""
RepoLens — Unit Tests: URL Validator
"""
import pytest
from backend.scanner.validator import validate_github_url, ValidationError, build_clone_args


class TestValidateGithubUrl:

    def test_valid_url(self):
        url, repo = validate_github_url("https://github.com/OWASP/NodeGoat")
        assert url == "https://github.com/OWASP/NodeGoat"
        assert repo == "OWASP/NodeGoat"

    def test_trailing_slash_stripped(self):
        url, repo = validate_github_url("https://github.com/owner/repo/")
        assert url == "https://github.com/owner/repo"

    def test_dot_git_stripped(self):
        url, repo = validate_github_url("https://github.com/owner/repo.git")
        assert repo == "owner/repo"

    def test_rejects_http(self):
        with pytest.raises(ValidationError, match="https://"):
            validate_github_url("http://github.com/owner/repo")

    def test_rejects_non_github(self):
        with pytest.raises(ValidationError, match="github.com"):
            validate_github_url("https://gitlab.com/owner/repo")

    def test_rejects_empty(self):
        with pytest.raises(ValidationError):
            validate_github_url("")

    def test_rejects_none_type(self):
        with pytest.raises((ValidationError, AttributeError, TypeError)):
            validate_github_url(None)  # type: ignore

    def test_rejects_shell_injection_semicolon(self):
        with pytest.raises(ValidationError):
            validate_github_url("https://github.com/owner/repo; rm -rf /")

    def test_rejects_shell_injection_backtick(self):
        with pytest.raises(ValidationError):
            validate_github_url("https://github.com/owner/`whoami`")

    def test_rejects_shell_injection_dollar(self):
        with pytest.raises(ValidationError):
            validate_github_url("https://github.com/owner/$(id)")

    def test_rejects_too_long(self):
        with pytest.raises(ValidationError):
            validate_github_url("https://github.com/owner/" + "a" * 2048)

    def test_rejects_url_with_port(self):
        with pytest.raises(ValidationError):
            validate_github_url("https://github.com:8080/owner/repo")

    def test_rejects_missing_repo(self):
        with pytest.raises(ValidationError):
            validate_github_url("https://github.com/onlyowner")

    def test_rejects_extra_path_segments(self):
        # Extra path like /owner/repo/tree/main should be rejected in MVP
        # (our regex requires exactly /owner/repo)
        with pytest.raises(ValidationError):
            validate_github_url("https://github.com/owner/repo/tree/main")

    def test_hyphenated_owner(self):
        url, repo = validate_github_url("https://github.com/my-org/my-repo")
        assert repo == "my-org/my-repo"


class TestBuildCloneArgs:

    def test_returns_list_not_shell_string(self):
        args = build_clone_args("https://github.com/owner/repo", "/tmp/dst")
        assert isinstance(args, list)
        assert "git" in args
        assert "--depth" in args
        assert "1" in args
        assert "--" in args  # explicit end of options
        assert "/tmp/dst" in args

    def test_no_shell_special_chars_in_args(self):
        args = build_clone_args("https://github.com/owner/repo", "/tmp/dst")
        combined = " ".join(args)
        # None of the shell-dangerous chars should appear in the repo URL arg
        for char in [";", "&", "|", "`", "$"]:
            assert char not in combined
