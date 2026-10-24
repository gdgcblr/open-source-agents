import urllib.error

import pytest

from review_core.analysis import links
from review_core.analysis.checks import run_deterministic_checks
from review_core.analysis.tools import REQUIRED_SECTIONS

SENTENCE = "This section explains the topic in enough detail for readers to follow along.\n"


def good_readme(extra=""):
    parts = ["# Demo\n", "Requires Python 3.11+.\n"]
    for section in REQUIRED_SECTIONS:
        parts.append(f"## {section.title()}\n{SENTENCE}")
        if section == "how to run":
            parts.append("```bash\npython main.py\n```\n")
    return "".join(parts) + extra


def make_project(tmp_path, name="good-agent", readme=None):
    root = tmp_path / name
    root.mkdir()
    (root / "README.md").write_text(readme if readme is not None else good_readme())
    (root / "main.py").write_text("print('hi')\n")
    (root / "requirements.txt").write_text("requests==2.32.0\n")
    (root / ".env.example").write_text("API_KEY=your_key_here\n")
    (root / ".gitignore").write_text(".env\n.venv/\n__pycache__/\n")
    return root


def results(path):
    return {c["id"]: c for c in run_deterministic_checks(str(path))["checks"]}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No test touches the network unless it patches these itself."""
    monkeypatch.setattr(links, "_is_public_host", lambda host: True)
    monkeypatch.setattr(links, "_fetch_status", lambda url: 200)


# ---- link checker ----------------------------------------------------------- #
def test_extract_urls_drops_placeholders_dupes_and_trailing_punctuation():
    text = (
        "See https://example.org/a. and https://example.org/a again, "
        "[x](https://example.org/b) and https://github.com/<user>/<repo>.git"
    )
    assert links.extract_urls(text) == ["https://example.org/a", "https://example.org/b"]


def test_urls_inside_code_are_not_checked():
    text = "Default `https://api.example.org/v1` and\n```bash\ncurl https://api.example.org/x\n```\nSee https://docs.example.org"
    assert links.extract_urls(text) == ["https://docs.example.org"]


def test_private_and_non_http_urls_are_skipped_without_a_request(monkeypatch):
    monkeypatch.undo()  # use the real host check, but forbid any request
    monkeypatch.setattr(links, "_fetch_status", lambda url: pytest.fail("request made"))
    assert links._check_one("http://127.0.0.1:8000/x")["state"] == "skipped"
    assert links._check_one("http://localhost/x")["state"] == "skipped"
    assert links._check_one("ftp://example.org/x")["state"] == "skipped"


@pytest.mark.parametrize("status,state", [(200, "ok"), (301, "ok"), (403, "ok"), (404, "broken"), (503, "broken")])
def test_status_to_state(monkeypatch, status, state):
    monkeypatch.setattr(links, "_fetch_status", lambda url: status)
    assert links._check_one("https://example.org")["state"] == state


def test_unverifiable_certificate_is_skipped_not_broken(monkeypatch):
    import ssl

    def bad_cert(url):
        raise urllib.error.URLError(ssl.SSLCertVerificationError("unable to get local issuer certificate"))

    monkeypatch.setattr(links, "_fetch_status", bad_cert)
    result = links._check_one("https://example.org")
    assert result["state"] == "skipped" and "certificate" in result["reason"]


def test_tls_context_always_verifies():
    import ssl

    ctx = links._tls_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname


def test_network_error_is_broken(monkeypatch):
    def boom(url):
        raise urllib.error.URLError("no route")

    monkeypatch.setattr(links, "_fetch_status", boom)
    result = links._check_one("https://example.org")
    assert result["state"] == "broken" and "network error" in result["reason"]


def test_check_links_reports_broken_and_caps_urls(tmp_path, monkeypatch):
    urls = " ".join(f"https://example.org/p{i}" for i in range(links.MAX_URLS + 5))
    root = make_project(tmp_path, readme=good_readme(urls))
    monkeypatch.setattr(links, "_fetch_status", lambda url: 404 if url.endswith("p0") else 200)
    result = links.check_links(str(root))
    assert result["truncated"] and result["checked"] == links.MAX_URLS
    assert [b["url"] for b in result["broken"]] == ["https://example.org/p0"]
    assert not result["passed"]


# ---- deterministic checks --------------------------------------------------- #
def test_good_project_passes_every_applicable_check(tmp_path):
    root = make_project(tmp_path)
    failed = [c for c in results(root).values() if c["applicable"] and not c["passed"]]
    assert failed == []


def test_every_check_has_the_documented_shape(tmp_path):
    for check in run_deterministic_checks(str(make_project(tmp_path)))["checks"]:
        assert set(check) == {"id", "criterion", "passed", "applicable", "reason"}
        assert check["criterion"] in {"reproducibility", "documentation", "security", "scope"}
        assert check["reason"]


def test_bad_project_fails_expected_checks(tmp_path):
    root = tmp_path / "My_Agent"
    root.mkdir()
    (root / "README.md").write_text("# [Project Name]\n## Overview\nShort.\n")
    (root / ".env").write_text("X=1\n")
    (root / "run.py").write_text('KEY = "AIza' + "A" * 35 + '"\n')
    r = results(root)
    failed = {i for i, c in r.items() if c["applicable"] and not c["passed"]}
    assert {"manifest_present", "env_example_present", "sections_present", "no_placeholders",
            "no_secrets", "gitignore_covers_secrets_and_venv", "folder_name_ok"} <= failed
    assert "AIza" + "A" * 35 not in str(r)


def test_missing_readme_fails_documentation(tmp_path):
    root = make_project(tmp_path)
    (root / "README.md").unlink()
    r = results(root)
    assert not r["readme_present"]["passed"]
    assert "sections_present" not in r


def test_unpinned_dependencies_fail(tmp_path):
    root = make_project(tmp_path)
    (root / "requirements.txt").write_text("requests\nflask>=2\npytest==9.1.1\n")
    check = results(root)["deps_pinned"]
    assert not check["passed"] and "requests" in check["reason"] and "pytest" not in check["reason"]


def test_pinning_not_applicable_without_requirements_txt(tmp_path):
    root = make_project(tmp_path)
    (root / "requirements.txt").unlink()
    (root / "package.json").write_text("{}")
    assert results(root)["deps_pinned"]["applicable"] is False


def test_python_version_only_applies_to_python_projects(tmp_path):
    root = make_project(tmp_path, readme=good_readme().replace("Python 3.11+", "a recent interpreter"))
    assert not results(root)["python_version_stated"]["passed"]
    (root / "requirements.txt").unlink()
    (root / "package.json").write_text("{}")
    assert results(root)["python_version_stated"]["applicable"] is False


def test_gitignore_must_cover_env_venv_and_pycache(tmp_path):
    root = make_project(tmp_path)
    (root / ".gitignore").write_text(".env\n")
    reason = results(root)["gitignore_covers_secrets_and_venv"]["reason"]
    assert "virtualenv" in reason and "__pycache__" in reason and ".env," not in reason


def test_run_command_must_be_in_a_code_block(tmp_path):
    readme = good_readme().replace("```bash\npython main.py\n```\n", "Just run it.\n")
    assert not results(make_project(tmp_path, readme=readme))["run_command_documented"]["passed"]


def test_pr_scope_not_applicable_to_an_untouched_folder(tmp_path):
    import subprocess

    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), "-c", "user.email=t@t", "-c", "user.name=t", *args],
                       check=True, capture_output=True)

    git("init", "-b", "main")
    untouched = make_project(tmp_path, name="untouched")
    git("add", "-A")
    git("commit", "-m", "init")
    git("checkout", "-b", "feat/x")
    (tmp_path / "elsewhere.txt").write_text("change in another folder")
    check = results(untouched)["pr_scope"]
    assert check["applicable"] is False and "no changes" in check["reason"]


def test_path_error_is_returned():
    assert "error" in run_deterministic_checks("does-not-exist")
