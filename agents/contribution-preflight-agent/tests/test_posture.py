import urllib.error

from preflight.posture import check_posture, dockerfile_findings


def messages(result: dict) -> list[str]:
    return [item["message"] for item in result["findings"]]


def severities(findings: list[dict]) -> set[str]:
    return {item["severity"] for item in findings}


def write_dockerfile(root, body: str):
    path = root / "Dockerfile"
    path.write_text(body)
    return path


def test_clean_project_passes(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests==2.32.3\n")
    write_dockerfile(tmp_path, "FROM python:3.12-slim\nUSER app\n")
    result = check_posture(str(tmp_path))
    assert result["status"] == "pass"
    assert result["findings"] == []
    assert len(result["components"]) == 1


def test_unpinned_dependency_warns(tmp_path):
    (tmp_path / "requirements.txt").write_text("flask>=3\n")
    result = check_posture(str(tmp_path))
    assert result["status"] == "warn"
    assert any("flask" in message for message in messages(result))


def test_npm_without_lockfile_warns(tmp_path):
    (tmp_path / "package.json").write_text('{"dependencies": {"left-pad": "1.3.0"}}')
    assert any("lockfile" in message for message in messages(check_posture(str(tmp_path))))
    (tmp_path / "package-lock.json").write_text("{}")
    assert not any("lockfile" in message for message in messages(check_posture(str(tmp_path))))


def test_dockerfile_latest_and_root(tmp_path):
    path = write_dockerfile(tmp_path, "FROM python:latest\nRUN echo hi\n")
    text = " ".join(item["message"] for item in dockerfile_findings(path))
    assert "no pinned tag" in text
    assert "runs as root" in text


def test_dockerfile_untagged_image(tmp_path):
    path = write_dockerfile(tmp_path, "FROM ubuntu\nUSER app\n")
    assert any("no pinned tag" in item["message"] for item in dockerfile_findings(path))


def test_dockerfile_digest_scratch_and_stage_ignored(tmp_path):
    body = "FROM golang:1.22 AS build\nFROM scratch\nFROM build\nFROM alpine@sha256:abc123\nUSER app\n"
    path = write_dockerfile(tmp_path, body)
    assert dockerfile_findings(path) == []


def test_dockerfile_secret_is_high(tmp_path):
    path = write_dockerfile(tmp_path, "FROM python:3.12-slim\nENV API_TOKEN=abc123\nUSER app\n")
    findings = dockerfile_findings(path)
    assert severities(findings) == {"high"}
    assert "API_TOKEN" in findings[0]["message"]


def test_dockerfile_secret_reference_and_bare_arg_not_flagged(tmp_path):
    path = write_dockerfile(tmp_path, "FROM python:3.12-slim\nARG API_TOKEN\nENV API_TOKEN=$API_TOKEN\nUSER app\n")
    assert dockerfile_findings(path) == []


def test_dockerfile_pipe_to_shell_and_continuations(tmp_path):
    body = "FROM python:3.12-slim\nRUN curl -fsSL https://example.org/install.sh \\\n    | sh\nUSER app\n"
    path = write_dockerfile(tmp_path, body)
    assert any("pipes it to a shell" in item["message"] for item in dockerfile_findings(path))


def test_root_user_counts_as_missing(tmp_path):
    path = write_dockerfile(tmp_path, "FROM python:3.12-slim\nUSER root\n")
    assert any("runs as root" in item["message"] for item in dockerfile_findings(path))


def test_vuln_scan_skipped_by_default(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests==2.32.3\n")

    def fail_fetch(components):
        raise AssertionError("network must not be used")

    result = check_posture(str(tmp_path), fetch=fail_fetch)
    assert result["vuln_scan"] == "skipped"


def test_vuln_scan_finds_issues(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests==2.32.3\nflask>=3\n")
    seen = {}

    def fake_fetch(components):
        seen["names"] = [item["name"] for item in components]
        return [["GHSA-demo-1234"]]

    result = check_posture(str(tmp_path), vuln_scan=True, fetch=fake_fetch)
    assert seen["names"] == ["requests"]
    assert result["status"] == "fail"
    assert result["vuln_scan"] == "done"
    assert result["vulnerabilities"] == [{"id": "GHSA-demo-1234", "ref": "pkg:pypi/requests@2.32.3"}]
    assert any("GHSA-demo-1234" in message for message in messages(result))


def test_vuln_scan_failure_is_warning_not_crash(tmp_path):
    (tmp_path / "requirements.txt").write_text("requests==2.32.3\n")

    def broken_fetch(components):
        raise urllib.error.URLError("offline")

    result = check_posture(str(tmp_path), vuln_scan=True, fetch=broken_fetch)
    assert result["vuln_scan"] == "failed"
    assert result["status"] == "warn"


def test_missing_directory(tmp_path):
    assert check_posture(str(tmp_path / "nope"))["status"] == "error"
