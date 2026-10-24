import csv
import json
import re
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
FILENAME = re.compile(r"^preflight_[a-z0-9-]+_[a-z0-9-]+_\d{8}-\d{6}")
COLUMNS = ["generated_utc", "project", "rules", "section", "check", "status", "detail"]


def run_cli(project: Path, reports: Path, *flags: str) -> subprocess.CompletedProcess:
    command = [sys.executable, "-m", "preflight", str(project), "--no-llm", "--out-dir", str(reports), *flags]
    return subprocess.run(command, cwd=APP_DIR, capture_output=True, text=True, timeout=120)


def make_good_project(base: Path) -> Path:
    root = base / "good-demo"
    root.mkdir()
    (root / "README.md").write_text("# Good Demo\n\nA small project with real documentation.\n")
    (root / ".gitignore").write_text(".env\n")
    (root / ".env.example").write_text("MODEL_NAME=gemma3:4b\n")
    (root / "requirements.txt").write_text("requests==2.32.3\n")
    (root / "Dockerfile").write_text("FROM python:3.12-slim\nUSER app\n")
    return root


def make_bad_project(base: Path) -> Path:
    root = base / "bad-demo"
    root.mkdir()
    (root / "README.md").write_text("# [Project Name]\n\n[One-sentence summary of the project]\n")
    (root / ".env").write_text("MODEL_NAME=x\n")
    (root / "settings.py").write_text('KEY = "' + "AIza" + "a" * 35 + '"\n')
    return root


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == COLUMNS
        return list(reader)


def files_by_suffix(reports: Path) -> dict:
    found = {}
    for path in reports.iterdir():
        if path.name.endswith("_sbom.cdx.json"):
            found["sbom"] = path
        else:
            found[path.suffix.lstrip(".")] = path
    return found


def assert_terminal_is_quiet(result: subprocess.CompletedProcess) -> None:
    lines = result.stdout.strip().splitlines()
    assert len(lines) == 1
    assert "Docs review" not in result.stdout
    assert not any(line.startswith("#") for line in lines)


def test_good_project_passes_and_writes_all_artifacts(tmp_path):
    reports = tmp_path / "reports"
    result = run_cli(make_good_project(tmp_path), reports)
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("Verdict: PASS")
    assert_terminal_is_quiet(result)
    found = files_by_suffix(reports)
    assert set(found) == {"csv", "pdf", "sbom"}
    for path in found.values():
        assert FILENAME.match(path.name)
    assert found["pdf"].read_bytes().startswith(b"%PDF")
    bom = json.loads(found["sbom"].read_text(encoding="utf-8"))
    assert bom["bomFormat"] == "CycloneDX"
    assert [item["name"] for item in bom["components"]] == ["requests"]


def test_good_project_csv_has_both_sections_and_passing_verdict(tmp_path):
    reports = tmp_path / "reports"
    run_cli(make_good_project(tmp_path), reports)
    rows = read_rows(files_by_suffix(reports)["csv"])
    assert {row["section"] for row in rows} == {"pr_preflight", "aspm", "summary"}
    checks = {(row["section"], row["check"]): row["status"] for row in rows}
    assert checks[("pr_preflight", "structure")] == "PASS"
    assert checks[("pr_preflight", "security")] == "PASS"
    assert checks[("aspm", "posture")] == "PASS"
    assert checks[("aspm", "sbom")] == "INFO"
    assert checks[("aspm", "vulnerability_scan")] == "INFO"
    assert checks[("summary", "verdict")] == "PASS"


def test_bad_project_fails_preflight(tmp_path):
    reports = tmp_path / "reports"
    result = run_cli(make_bad_project(tmp_path), reports, "--profile", "gdgcblr")
    assert result.returncode == 1
    assert result.stdout.startswith("Verdict: FAIL")
    assert_terminal_is_quiet(result)
    rows = read_rows(files_by_suffix(reports)["csv"])
    failed = {row["check"] for row in rows if row["section"] == "pr_preflight" and row["status"] == "FAIL"}
    assert {"structure", "security"} <= failed
    assert {row["rules"] for row in rows} == {"gdgcblr"}


def test_no_aspm_skips_sbom_and_aspm_rows(tmp_path):
    reports = tmp_path / "reports"
    result = run_cli(make_good_project(tmp_path), reports, "--no-aspm")
    assert result.returncode == 0, result.stderr
    found = files_by_suffix(reports)
    assert set(found) == {"csv", "pdf"}
    assert "aspm" not in {row["section"] for row in read_rows(found["csv"])}


def test_csv_format_writes_csv_and_sbom_only(tmp_path):
    reports = tmp_path / "reports"
    result = run_cli(make_good_project(tmp_path), reports, "--format", "csv")
    assert result.returncode == 0, result.stderr
    assert set(files_by_suffix(reports)) == {"csv", "sbom"}


def test_unpinned_dependency_and_dockerfile_secret_fail_verdict(tmp_path):
    project = make_good_project(tmp_path)
    (project / "requirements.txt").write_text("requests==2.32.3\nflask>=3\n")
    (project / "Dockerfile").write_text("FROM python:3.12-slim\nENV API_TOKEN=abc123\nUSER app\n")
    reports = tmp_path / "reports"
    result = run_cli(project, reports)
    assert result.returncode == 1
    assert result.stdout.startswith("Verdict: FAIL")
    rows = read_rows(files_by_suffix(reports)["csv"])
    posture = {row["status"] for row in rows if row["section"] == "aspm" and row["check"] == "posture"}
    assert {"WARN", "HIGH"} <= posture
    assert any("flask" in row["detail"] for row in rows if row["status"] == "WARN")
    assert any("API_TOKEN" in row["detail"] for row in rows if row["status"] == "HIGH")


def test_warnings_alone_do_not_fail_the_verdict(tmp_path):
    project = make_good_project(tmp_path)
    (project / "requirements.txt").write_text("requests==2.32.3\nflask>=3\n")
    reports = tmp_path / "reports"
    result = run_cli(project, reports)
    assert result.returncode == 0, result.stderr
    rows = read_rows(files_by_suffix(reports)["csv"])
    assert any(row["status"] == "WARN" for row in rows)
    assert result.stdout.startswith("Verdict: PASS")


def test_unknown_profile_is_reported_and_fails(tmp_path):
    reports = tmp_path / "reports"
    result = run_cli(make_good_project(tmp_path), reports, "--profile", "nope")
    assert result.returncode == 1
    assert_terminal_is_quiet(result)
    rows = read_rows(files_by_suffix(reports)["csv"])
    structure = [row for row in rows if row["check"] == "structure"]
    assert any("Unknown profile" in row["detail"] for row in structure)


def test_vuln_scan_is_off_by_default(tmp_path):
    reports = tmp_path / "reports"
    run_cli(make_good_project(tmp_path), reports)
    rows = read_rows(files_by_suffix(reports)["csv"])
    scan = next(row for row in rows if row["check"] == "vulnerability_scan")
    assert scan["detail"].startswith("skipped")
