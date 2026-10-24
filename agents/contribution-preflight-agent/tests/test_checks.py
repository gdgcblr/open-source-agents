from pathlib import Path

from preflight.checks import check_security, check_structure, collect_docs
from preflight.rules import load_profile

RULES = load_profile("gdgcblr")


def make_project(base: Path, name: str = "good-project") -> Path:
    root = base / name
    root.mkdir()
    (root / "README.md").write_text("# Good Project\n\nReal documentation.\n")
    (root / ".gitignore").write_text(".env\n")
    (root / ".env.example").write_text("MODEL_NAME=gemma3:4b\n")
    (root / "requirements.txt").write_text("requests==2.32.3\n")
    (root / "Dockerfile").write_text("FROM python:3.12-slim\n")
    return root


def test_clean_project_passes(tmp_path):
    root = make_project(tmp_path)
    assert check_structure(str(root), RULES)["status"] == "pass"
    assert check_security(str(root))["status"] == "pass"


def test_bad_name_flagged(tmp_path):
    root = make_project(tmp_path, "Bad_Name")
    findings = check_structure(str(root), RULES)["findings"]
    assert any("kebab-case" in f for f in findings)


def test_generic_name_flagged(tmp_path):
    root = make_project(tmp_path, "demo")
    findings = check_structure(str(root), RULES)["findings"]
    assert any("too generic" in f for f in findings)


def test_missing_files_flagged(tmp_path):
    root = make_project(tmp_path)
    (root / ".gitignore").unlink()
    (root / "requirements.txt").unlink()
    findings = check_structure(str(root), RULES)["findings"]
    assert any(".gitignore" in f for f in findings)
    assert any("manifest" in f for f in findings)


def test_template_placeholder_flagged(tmp_path):
    root = make_project(tmp_path)
    (root / "README.md").write_text("# [Project Name]\n")
    findings = check_structure(str(root), RULES)["findings"]
    assert any("placeholder" in f for f in findings)


def test_placeholder_inside_code_fence_ignored(tmp_path):
    root = make_project(tmp_path)
    (root / "README.md").write_text("# Real Title\n\n```\n- README still contains: [Project Name]\n```\n")
    assert check_structure(str(root), RULES)["status"] == "pass"


def test_env_file_flagged(tmp_path):
    root = make_project(tmp_path)
    (root / ".env").write_text("X=1\n")
    findings = check_security(str(root))["findings"]
    assert any(".env" in f for f in findings)


def test_secret_in_source_flagged(tmp_path):
    root = make_project(tmp_path)
    (root / "main.py").write_text('KEY = "AIza' + "a" * 35 + '"\n')
    findings = check_security(str(root))["findings"]
    assert any("Google API key" in f for f in findings)


def test_env_example_is_allowed(tmp_path):
    root = make_project(tmp_path)
    assert check_security(str(root))["status"] == "pass"


def test_ignored_dirs_not_scanned(tmp_path):
    root = make_project(tmp_path)
    (root / "node_modules").mkdir()
    (root / "node_modules" / "x.js").write_text('k = "AIza' + "a" * 35 + '"\n')
    assert check_security(str(root))["status"] == "pass"


def test_missing_directory_errors(tmp_path):
    assert check_structure(str(tmp_path / "nope"), RULES)["status"] == "error"


def test_collect_docs(tmp_path):
    root = make_project(tmp_path)
    docs = collect_docs(str(root))
    assert docs["status"] == "ok"
    assert "Real documentation" in docs["readme"]
    assert "README.md" in docs["files"]
