"""Tests for R07 (secrets), R08 (hygiene), and R11 (deps)."""
from __future__ import annotations

from pathlib import Path

import pytest

from contrib_audit.rules.secrets import scan_secrets, check_hygiene
from contrib_audit.rules.deps import check_imports_declared
from contrib_audit.models import Severity


# ---------------------------------------------------------------------------
# R07 secrets
# ---------------------------------------------------------------------------

def make_proj(tmp_path: Path) -> Path:
    p = tmp_path / "agents" / "cool-agent"
    p.mkdir(parents=True)
    (p / ".gitignore").write_text(".env\n.venv/\nvenv/\n")
    return p


class TestR07:
    def test_no_secrets(self, tmp_path):
        proj = make_proj(tmp_path)
        (proj / "main.py").write_text('key = "your_api_key_here"\n')
        findings = scan_secrets(proj)
        assert not findings

    def test_google_api_key_detected(self, tmp_path):
        proj = make_proj(tmp_path)
        # Built at runtime from fragments — never a real key
        fake = "AIza" + "B" * 35
        (proj / "bad.py").write_text(f'KEY = "{fake}"\n')
        findings = scan_secrets(proj)
        assert any(f.rule_id == "R07" and f.severity == Severity.ERROR for f in findings)

    def test_evidence_is_redacted(self, tmp_path):
        proj = make_proj(tmp_path)
        fake = "AIza" + "C" * 35
        (proj / "bad.py").write_text(f'KEY = "{fake}"\n')
        findings = scan_secrets(proj)
        assert findings
        for f in findings:
            if f.evidence:
                assert "..." in f.evidence
                assert len(f.evidence) <= 10  # first 4 + "..."

    def test_openai_key_detected(self, tmp_path):
        proj = make_proj(tmp_path)
        fake = "sk-" + "x" * 25
        (proj / "bad.py").write_text(f'TOKEN = "{fake}"\n')
        findings = scan_secrets(proj)
        assert any(f.rule_id == "R07" for f in findings)

    def test_github_token_detected(self, tmp_path):
        proj = make_proj(tmp_path)
        fake = "ghp_" + "A" * 40
        (proj / "bad.py").write_text(f'TOKEN = "{fake}"\n')
        findings = scan_secrets(proj)
        assert any(f.rule_id == "R07" for f in findings)

    def test_aws_key_detected(self, tmp_path):
        proj = make_proj(tmp_path)
        fake = "AKIA" + "A" * 16
        (proj / "bad.py").write_text(f'ACCESS_KEY = "{fake}"\n')
        findings = scan_secrets(proj)
        assert any(f.rule_id == "R07" for f in findings)

    def test_pem_block_detected(self, tmp_path):
        proj = make_proj(tmp_path)
        (proj / "key.txt").write_text("-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n")
        findings = scan_secrets(proj)
        assert any(f.rule_id == "R07" for f in findings)

    def test_placeholder_not_flagged(self, tmp_path):
        proj = make_proj(tmp_path)
        (proj / ".env.example").write_text("GOOGLE_API_KEY=your_google_api_key_here\n")
        findings = scan_secrets(proj)
        r07 = [f for f in findings if f.rule_id == "R07"]
        assert not r07

    def test_git_dir_skipped(self, tmp_path):
        proj = make_proj(tmp_path)
        git_dir = proj / ".git"
        git_dir.mkdir()
        fake = "AIza" + "D" * 35
        (git_dir / "config").write_text(f"KEY={fake}\n")
        findings = scan_secrets(proj)
        assert not any(f.rule_id == "R07" for f in findings)

    def test_generic_assignment_long_literal(self, tmp_path):
        proj = make_proj(tmp_path)
        # A suspiciously long literal that is not a placeholder
        (proj / "cfg.py").write_text('SECRET = "aB3dE6fG8hI1jK4lM7nO0pQ2"\n')
        findings = scan_secrets(proj)
        assert any(f.rule_id == "R07" for f in findings)


# ---------------------------------------------------------------------------
# R08 hygiene
# ---------------------------------------------------------------------------

class TestR08:
    def test_clean(self, tmp_path):
        proj = make_proj(tmp_path)
        findings = check_hygiene(proj)
        assert not findings

    def test_env_file_detected(self, tmp_path):
        proj = make_proj(tmp_path)
        (proj / ".env").write_text("SECRET=real_secret\n")
        findings = check_hygiene(proj)
        assert any(f.rule_id == "R08" and f.severity == Severity.ERROR for f in findings)

    def test_venv_dir_detected(self, tmp_path):
        proj = make_proj(tmp_path)
        venv = proj / ".venv"
        venv.mkdir()
        (venv / "pyvenv.cfg").write_text("home = /usr/bin\n")
        findings = check_hygiene(proj)
        assert any(f.rule_id == "R08" for f in findings)

    def test_sqlite_db_detected(self, tmp_path):
        proj = make_proj(tmp_path)
        (proj / "local.db").write_bytes(b"SQLite format 3\x00" + b"\x00" * 84)
        findings = check_hygiene(proj)
        assert any(f.rule_id == "R08" for f in findings)

    def test_gitignore_missing_env(self, tmp_path):
        proj = make_proj(tmp_path)
        (proj / ".gitignore").write_text("# nothing\nvenv/\n")
        findings = check_hygiene(proj)
        assert any(f.rule_id == "R08" and ".env" in f.message for f in findings)

    def test_gitignore_missing_venv(self, tmp_path):
        proj = make_proj(tmp_path)
        (proj / ".gitignore").write_text(".env\n# no venv\n")
        findings = check_hygiene(proj)
        assert any(f.rule_id == "R08" and "virtual environment" in f.message for f in findings)


# ---------------------------------------------------------------------------
# R11 deps
# ---------------------------------------------------------------------------

class TestR11:
    def test_declared_import_ok(self, tmp_path):
        proj = make_proj(tmp_path)
        (proj / "requirements.txt").write_text("requests>=2.0\n")
        (proj / "main.py").write_text("import requests\n")
        findings = check_imports_declared(proj)
        assert not any(f.rule_id == "R11" and "requests" in str(f.evidence) for f in findings)

    def test_undeclared_import_warned(self, tmp_path):
        proj = make_proj(tmp_path)
        (proj / "requirements.txt").write_text("# nothing\n")
        (proj / "main.py").write_text("import httpx\n")
        findings = check_imports_declared(proj)
        assert any(f.rule_id == "R11" and "httpx" in str(f.evidence) for f in findings)

    def test_stdlib_not_flagged(self, tmp_path):
        proj = make_proj(tmp_path)
        (proj / "requirements.txt").write_text("# nothing\n")
        (proj / "main.py").write_text(
            "import os\nimport pathlib\nimport re\nimport json\n"
        )
        findings = check_imports_declared(proj)
        assert not any(f.rule_id == "R11" for f in findings)
