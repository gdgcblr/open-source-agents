"""Comprehensive unit tests for MergeReady checks and rules."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import pytest

from merge_ready.checks import CHECK_REGISTRY, OPTIONAL_RULES, REQUIRED_RULES, run_all_checks
from merge_ready.checks.agent_safety import decode_tag_chars, scan_unicode
from merge_ready.checks.deps import IMPORT_ALIAS_MAP, normalize_package_name
from merge_ready.checks.layout import check_f01, check_l02
from merge_ready.checks.secrets import is_placeholder, redact_secret, shannon_entropy
from merge_ready.model import Finding, RuleResult, Severity, ValidationReport, Verdict
from merge_ready.project import ProjectContext

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_good_tool_passes_all_checks():
    """Verify that the golden good-tool fixture produces zero failures and passes."""
    ctx = ProjectContext(project_path=FIXTURES_DIR / "good-tool")
    report = run_all_checks(ctx)

    assert not report.has_failures, f"Good tool failed unexpectedly: {report.to_dict()}"
    assert report.summary["fail"] == 0
    assert report.summary["errors"] == 0
    # Must pass core layout, files, template, and safety rules
    assert report.results["L01"].verdict == Verdict.PASS
    assert report.results["L02"].verdict == Verdict.PASS
    assert report.results["F01"].verdict == Verdict.PASS
    assert report.results["D01"].verdict == Verdict.PASS
    assert report.results["S01"].verdict == Verdict.PASS
    assert report.results["S02"].verdict == Verdict.PASS
    assert report.results["A02"].verdict == Verdict.PASS


def test_bad_agent_triggers_expected_rules(defective_agent_dir: Path):
    """Verify that defective fixture triggers expected failures and warnings."""
    ctx = ProjectContext(project_path=defective_agent_dir)
    report = run_all_checks(ctx)

    assert report.has_failures, "Bad agent should have failed validation"
    # D01: Template residue
    assert report.results["D01"].verdict == Verdict.FAIL
    assert any("[Project Name]" in f.evidence for f in report.results["D01"].findings)

    # S01: Secret exposure
    assert report.results["S01"].verdict == Verdict.FAIL
    bad_key = "AIza" + "SyD9a8b7c6d5e4f3g2h1j0k9l8m7n6b5v4c"
    for f in report.results["S01"].findings:
        assert bad_key not in (f.evidence or "")
    assert any("[REDACTED]" in (f.evidence or "") for f in report.results["S01"].findings)

    # S02: Local database tracked/present
    assert report.results["S02"].verdict == Verdict.FAIL
    assert any(".sqlite" in f.path for f in report.results["S02"].findings)

    # E01: Undocumented env var
    assert report.results["E01"].verdict == Verdict.FAIL
    assert any("SECRET_BACKDOOR_KEY" in f.message for f in report.results["E01"].findings)

    # R01: Missing manifest dependency (yaml)
    assert report.results["R01"].verdict == Verdict.WARN
    assert any("yaml" in f.message or "pyyaml" in f.message for f in report.results["R01"].findings)

    # A01: Unbounded execution loop
    assert report.results["A01"].verdict == Verdict.WARN
    assert any("unbounded" in f.message.lower() for f in report.results["A01"].findings)

    # A02: Hidden Unicode
    assert report.results["A02"].verdict == Verdict.FAIL
    assert any("bidirectional" in f.message.lower() or "tag character" in f.message.lower() for f in report.results["A02"].findings)

    # A03: High-impact subprocess execution
    assert report.results["A03"].verdict == Verdict.WARN
    assert any("subprocess" in f.message for f in report.results["A03"].findings)


def test_invalid_project_name_l02(tmp_path: Path):
    """L02: Test kebab-case and generic name blocklist."""
    # 1. Uppercase / spaces
    bad_dir = tmp_path / "My Agent"
    bad_dir.mkdir()
    ctx1 = ProjectContext(project_path=bad_dir)
    res1 = check_l02(ctx1, {})
    assert res1.verdict == Verdict.FAIL
    assert any("kebab-case" in f.message for f in res1.findings)

    # 2. Generic name
    generic_dir = tmp_path / "my-agent"
    generic_dir.mkdir()
    ctx2 = ProjectContext(project_path=generic_dir)
    res2 = check_l02(ctx2, {})
    assert res2.verdict == Verdict.FAIL
    assert any("generic" in f.message for f in res2.findings)


def test_missing_required_files_f01(tmp_path: Path):
    """F01: Missing required files produce explicit errors."""
    empty_proj = tmp_path / "empty-tool"
    empty_proj.mkdir()
    ctx = ProjectContext(project_path=empty_proj)
    report = run_all_checks(ctx)

    assert report.results["F01"].verdict == Verdict.FAIL
    missing_msgs = [f.message for f in report.results["F01"].findings]
    assert any("README.md" in m for m in missing_msgs)
    assert any(".env.example" in m for m in missing_msgs)
    assert any(".gitignore" in m for m in missing_msgs)
    assert any("manifest" in m for m in missing_msgs)


def test_secrets_redaction_and_entropy_negative_controls():
    """S01: Test negative controls (UUID, Git SHA, placeholders) and redaction."""
    # Redaction
    raw_secret = "AIza" + "SyD12345678901234567890123456789"
    redacted = redact_secret(raw_secret)
    assert raw_secret not in redacted
    assert "[REDACTED]" in redacted

    # Placeholders
    assert is_placeholder("your_api_key_here")
    assert is_placeholder("<your-token>")
    assert is_placeholder("DUMMY_KEY_VALUE")
    assert not is_placeholder("ghp_" + "123456789012345678901234567890123456")

    # Shannon entropy computation
    low_ent = shannon_entropy("aaaaaaaaaaaaaaaaaaaa")
    high_ent = shannon_entropy("w9Xz+7bM/Q2eR4tY1uI8")
    assert low_ent < 1.0
    assert high_ent > 4.0


def test_hidden_unicode_and_tag_decoding():
    """A02: Test bidi characters, hidden tags, and tag payload decoding."""
    # Legitimate emoji with ZWJ (U+200D) should not trigger ERROR
    emoji_text = "Hello 👩‍💻 world!"
    findings = scan_unicode(emoji_text)
    error_findings = [f for f in findings if f[0] == Severity.ERROR]
    assert len(error_findings) == 0

    # Tag characters for 'P', 'W', 'N'
    tag_pwn = "\U000E0050\U000E0057\U000E004E"
    decoded = decode_tag_chars(tag_pwn)
    assert decoded == "PWN"

    # Scan detects tag chars as ERROR
    findings_tag = scan_unicode(tag_pwn)
    assert any(f[0] == Severity.ERROR and "tag" in f[4].lower() for f in findings_tag)

    # Bidi override detected
    bidi_str = "Code with \u202E override"
    findings_bidi = scan_unicode(bidi_str)
    assert any(f[0] == Severity.ERROR and "bidirectional" in f[4].lower() for f in findings_bidi)


def test_dependency_manifest_alias_normalization():
    """R01: Verify normalization and package alias mapping."""
    assert normalize_package_name("PyYAML") == "pyyaml"
    assert normalize_package_name("google_genai") == "google-genai"
    assert normalize_package_name("google.adk") == "google-adk"
    assert IMPORT_ALIAS_MAP["google.genai"] == "google-genai"
    assert IMPORT_ALIAS_MAP["yaml"] == "pyyaml"
    assert IMPORT_ALIAS_MAP["PIL"] == "pillow"


def test_scope_diff_validation_with_git(tmp_path: Path):
    """P01 & I01: Verify diff scope using a temporary Git repository."""
    repo = tmp_path / "test-repo"
    repo.mkdir()

    # 1. Initialize git repo
    subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True)

    # Create root files & base branch
    (repo / "tools").mkdir()
    (repo / "tools" / "README.md").write_text("# Tools\n| Tool | Description |\n| :--- | :--- |\n| *(None yet)* | — |\n")
    (repo / "CONTRIBUTING.md").write_text("Contributing guidelines")
    (repo / "template").mkdir()
    (repo / "template" / "README.md").write_text("# [Project Name]\n## Overview\n## License\n")
    (repo / "template" / ".env.example").write_text("# API_KEY=xxx\n")
    (repo / "template" / ".gitignore").write_text(".venv/\n")

    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-m", "Initial upstream commit"], cwd=str(repo), check=True)
    subprocess.run(["git", "branch", "-M", "main"], cwd=str(repo), check=True)

    # 2. Create feature branch and add valid tool
    subprocess.run(["git", "checkout", "-b", "feat/my-clean-tool"], cwd=str(repo), check=True)
    my_tool = repo / "tools" / "my-clean-tool"
    my_tool.mkdir()
    (my_tool / "README.md").write_text("# My Clean Tool\n## Overview\nClean tool.\n## License\nMIT\n")
    (my_tool / ".env.example").write_text("# API_KEY=xxx\n")
    (my_tool / ".gitignore").write_text(".venv/\n")
    (my_tool / "requirements.txt").write_text("pytest\n")

    # Update index table by replacing None yet row
    (repo / "tools" / "README.md").write_text("# Tools\n| Tool | Description |\n| :--- | :--- |\n| [my-clean-tool](my-clean-tool/) | Clean utility |\n")

    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-m", "feat: add my-clean-tool"], cwd=str(repo), check=True)

    # Validate with base=main
    ctx = ProjectContext(project_path=my_tool, base_ref="main")
    report = run_all_checks(ctx)
    assert report.results["P01"].verdict == Verdict.PASS
    assert report.results["I01"].verdict == Verdict.PASS

    # 3. Corrupt scope: modify root CONTRIBUTING.md
    (repo / "CONTRIBUTING.md").write_text("Modified root guidelines out of scope")
    subprocess.run(["git", "add", "CONTRIBUTING.md"], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-m", "corrupt scope"], cwd=str(repo), check=True)

    ctx_bad = ProjectContext(project_path=my_tool, base_ref="main")
    report_bad = run_all_checks(ctx_bad)
    assert report_bad.results["P01"].verdict == Verdict.FAIL
    assert any("CONTRIBUTING.md" in f.path for f in report_bad.results["P01"].findings)


def test_false_positive_placeholder_secrets(tmp_path: Path):
    """S01: Ensure template placeholders and obvious fake values do not trigger secret findings."""
    proj = tmp_path / "tools" / "test-placeholders"
    proj.mkdir(parents=True)
    (proj / "README.md").write_text("# Test Placeholders\n## Overview\nTest\n## License\nMIT\n")
    (proj / ".gitignore").write_text(".venv/\n")
    (proj / ".env.example").write_text(
        "# API_KEY=your_gemini_api_key_here\n"
        "# SECRET_TOKEN=<your-secret-token>\n"
        "# CLIENT_SECRET=${CLIENT_SECRET_PLACEHOLDER}\n"
    )
    (proj / "requirements.txt").write_text("pytest\n")
    (proj / "main.py").write_text(
        '# Documented and placeholder assignments\n'
        'DEFAULT_PLACEHOLDER = "your_api_key_here"\n'
        'DUMMY_KEY = "dummy_token_12345678901234567890"\n'
        'SAMPLE_ENV = "<INSERT_KEY_HERE>"\n'
        'CONFIG_NONE = "none"\n'
    )

    ctx = ProjectContext(project_path=proj)
    report = run_all_checks(ctx)
    assert report.results["S01"].verdict == Verdict.PASS, f"Placeholders triggered false positive: {report.results['S01'].findings}"


def test_false_positive_uuids_and_git_shas(tmp_path: Path):
    """S01: Ensure UUIDs, urn:uuid, and Git commit hashes do not trigger secret findings."""
    proj = tmp_path / "tools" / "test-identifiers"
    proj.mkdir(parents=True)
    (proj / "README.md").write_text("# Test Identifiers\n## Overview\nTest\n## License\nMIT\n")
    (proj / ".gitignore").write_text(".venv/\n")
    (proj / ".env.example").write_text("# API_KEY=placeholder\n")
    (proj / "requirements.txt").write_text("pytest\n")
    (proj / "main.py").write_text(
        '# Standard UUIDs and Git SHAs\n'
        'user_id = "c9bf9e57-1685-4c89-bafb-ff5af830be8a"\n'
        'urn_uuid = "urn:uuid:6ba7b810-9dad-11d1-80b4-00c04fd430c8"\n'
        'git_commit_sha = "b0ad2a403b7dc731f3b5e2d5e9ba0fe07f6d4b36"\n'
        'sha256_hash = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"\n'
        'auth_token = "123e4567-e89b-12d3-a456-426614174000"\n'
    )

    ctx = ProjectContext(project_path=proj)
    report = run_all_checks(ctx)
    assert report.results["S01"].verdict == Verdict.PASS, f"Identifiers triggered false positive: {report.results['S01'].findings}"


def test_false_positive_normal_unicode_multilingual_and_emojis():
    """A02: Ensure international text, legitimate RTL marks, and composite emojis do not trigger errors."""
    # Multilingual text
    intl_text = (
        "English: Hello World!\n"
        "French: Déjà vu au café.\n"
        "German: Übergrößenträger.\n"
        "Spanish: ¿Cómo estás, señor?\n"
        "Hebrew with LTR/RTL marks: \u200Eשלום עולם!\u200F\n"
        "Arabic: مرحبا بالعالم\n"
        "Japanese: こんにちは世界\n"
        "Hindi: नमस्ते दुनिया\n"
        "Mathematical: ∀x ∈ ℝ, x² ≥ 0.\n"
    )
    intl_findings = scan_unicode(intl_text)
    intl_errors = [f for f in intl_findings if f[0] == Severity.ERROR]
    assert len(intl_errors) == 0, f"Normal multilingual text triggered Unicode error: {intl_errors}"

    # Composite emojis with Zero-Width Joiner (U+200D)
    emoji_text = "Family: 👨‍👩‍👧‍👦, Technologist: 👩‍💻, Rainbow Flag: 🏳️‍🌈, Thumbs up: 👍"
    emoji_findings = scan_unicode(emoji_text)
    emoji_errors = [f for f in emoji_findings if f[0] == Severity.ERROR]
    assert len(emoji_errors) == 0, f"Legitimate emojis triggered Unicode error: {emoji_errors}"


def test_false_positive_commented_environment_variables(tmp_path: Path):
    """E01: Ensure commented-out variables in .env.example are accepted as documented."""
    proj = tmp_path / "tools" / "test-commented-env"
    proj.mkdir(parents=True)
    (proj / "README.md").write_text(
        "# Test Commented Env\n"
        "## Overview\nTest\n"
        "## Configuration & Environment Variables\n"
        "| Variable Name | Required | Default | Description |\n"
        "| :--- | :--- | :--- | :--- |\n"
        "| `GEMINI_API_KEY` | Yes | None | LLM API Key |\n"
        "| `DB_PORT` | No | 5432 | Database port |\n"
        "## License\nMIT\n"
    )
    (proj / ".gitignore").write_text(".venv/\n")
    # Commented out in .env.example
    (proj / ".env.example").write_text(
        "# LLM Configuration:\n"
        "# GEMINI_API_KEY=your_key_here\n"
        "# DB_PORT=5432\n"
    )
    (proj / "requirements.txt").write_text("pytest\n")
    (proj / "main.py").write_text(
        "import os\n"
        "api_key = os.getenv('GEMINI_API_KEY')\n"
        "port = os.environ.get('DB_PORT', '5432')\n"
    )

    ctx = ProjectContext(project_path=proj)
    report = run_all_checks(ctx)
    assert report.results["E01"].verdict == Verdict.PASS, f"Commented env vars triggered error: {report.results['E01'].findings}"


def test_false_positive_standard_library_and_local_imports(tmp_path: Path):
    """R01: Ensure standard-library and local intra-project imports do not trigger missing dependency warnings."""
    proj = tmp_path / "tools" / "test-imports"
    proj.mkdir(parents=True)
    (proj / "README.md").write_text("# Test Imports\n## Overview\nTest\n## License\nMIT\n")
    (proj / ".gitignore").write_text(".venv/\n")
    (proj / ".env.example").write_text("# API_KEY=placeholder\n")
    (proj / "requirements.txt").write_text("pytest>=8.0.0\n")

    # Local package
    pkg_dir = proj / "helper_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("def assist(): pass\n")

    (proj / "main.py").write_text(
        "import sys\n"
        "import os\n"
        "import json\n"
        "import math\n"
        "import re\n"
        "import pathlib\n"
        "import typing\n"
        "import dataclasses\n"
        "import argparse\n"
        "import tomllib\n"
        "import subprocess\n"
        "from helper_pkg import assist\n"
    )

    ctx = ProjectContext(project_path=proj)
    report = run_all_checks(ctx)
    assert report.results["R01"].verdict == Verdict.PASS, f"Stdlib/local imports triggered warning: {report.results['R01'].findings}"


def test_false_positive_legitimate_loops_and_bounded_whiles(tmp_path: Path):
    """A01: Ensure for-loops, while-loops with counter/break/return, and non-model whiles do not trigger A01."""
    proj = tmp_path / "tools" / "test-loops"
    proj.mkdir(parents=True)
    (proj / "README.md").write_text("# Test Loops\n## Overview\nTest\n## License\nMIT\n")
    (proj / ".gitignore").write_text(".venv/\n")
    (proj / ".env.example").write_text("# API_KEY=placeholder\n")
    (proj / "requirements.txt").write_text("pytest\n")
    (proj / "main.py").write_text(
        "class MockAgent:\n"
        "    def chat(self, prompt):\n"
        "        return 'resp'\n"
        "\n"
        "def process():\n"
        "    agent = MockAgent()\n"
        "    # 1. Bounded for loop\n"
        "    for i in range(5):\n"
        "        agent.chat('hello')\n"
        "    # 2. While loop with comparison test\n"
        "    count = 0\n"
        "    while count < 3:\n"
        "        agent.chat('step')\n"
        "        count += 1\n"
        "    # 3. while True with explicit break\n"
        "    while True:\n"
        "        res = agent.chat('query')\n"
        "        if res:\n"
        "            break\n"
        "    # 4. while True with explicit return\n"
        "    while True:\n"
        "        return agent.chat('final')\n"
    )

    ctx = ProjectContext(project_path=proj)
    report = run_all_checks(ctx)
    assert report.results["A01"].verdict == Verdict.PASS, f"Legitimate loops triggered A01 warning: {report.results['A01'].findings}"


def test_secret_redaction_across_all_report_formats(tmp_path: Path):
    """S01 & Reporting: Ensure raw credentials are never leaked in terminal, json, or markdown reports."""
    from merge_ready.report import format_terminal, format_json, format_markdown, format_github_annotations

    proj = tmp_path / "tools" / "leak-test"
    proj.mkdir(parents=True)
    (proj / "README.md").write_text("# Leak Test\n## Overview\nTest\n## License\nMIT\n")
    (proj / ".gitignore").write_text(".venv/\n")
    (proj / ".env.example").write_text("# API_KEY=placeholder\n")
    (proj / "requirements.txt").write_text("pytest\n")

    # Real-shaped fake Google key
    raw_secret = "AIza" + "SyB8c7d6e5f4g3h2j1k0l9m8n7b6v5c4x3z"
    (proj / "main.py").write_text(f'API_KEY = "{raw_secret}"\n')

    ctx = ProjectContext(project_path=proj)
    report = run_all_checks(ctx)
    assert report.results["S01"].verdict == Verdict.FAIL

    term_out = format_terminal(report)
    json_out = format_json(report)
    md_out = format_markdown(report)
    gh_out = format_github_annotations(report)

    for output_name, text in [("terminal", term_out), ("json", json_out), ("markdown", md_out), ("github", gh_out)]:
        assert raw_secret not in text, f"Raw secret leaked in {output_name} report!"
        assert "[REDACTED]" in text or output_name == "github", f"Redacted tag missing in {output_name} report!"


def test_static_checks_never_execute_inspected_code(tmp_path: Path):
    """Safety: Verify that MergeReady never executes, imports, or runs inspected contributor code."""
    proj = tmp_path / "tools" / "untrusted-code"
    proj.mkdir(parents=True)
    (proj / "README.md").write_text("# Untrusted Code\n## Overview\nTest\n## License\nMIT\n")
    (proj / ".gitignore").write_text(".venv/\n")
    (proj / ".env.example").write_text("# API_KEY=placeholder\n")
    (proj / "requirements.txt").write_text("pytest\n")

    sentinel_file = proj / "SENTINEL_EXECUTED.txt"
    # If this code were executed (via import, eval, exec, or python run), it would create the sentinel file
    (proj / "malicious_script.py").write_text(
        f"import pathlib\n"
        f"pathlib.Path(r'{sentinel_file}').write_text('EXECUTED_FAIL')\n"
    )

    ctx = ProjectContext(project_path=proj)
    report = run_all_checks(ctx)

    # Prove that the code was never executed
    assert not sentinel_file.exists(), "CRITICAL SAFETY VIOLATION: Contributor code was executed during validation!"


def test_nested_fixture_directory_security_scanning(tmp_path: Path):
    """Exclusion audit: Prove that nested fixture/test directories are not exempted from security scans."""
    proj = tmp_path / "agents" / "nested-fixture-agent"
    proj.mkdir(parents=True)
    (proj / "README.md").write_text("# Nested Fixture Agent\n## Overview\nValid\n## License\nMIT\n")
    (proj / ".env.example").write_text("API_KEY=placeholder\n")
    (proj / ".gitignore").write_text(".venv/\n")
    (proj / "requirements.txt").write_text("pytest\n")

    # 1. Nested secret fixture inside tests/fixtures/data/
    nested_dir = proj / "tests" / "fixtures" / "data"
    nested_dir.mkdir(parents=True)
    secret_val = "AIza" + "Sy" + "TestSecret12345678901234567890123"
    (nested_dir / "secret_fixture.py").write_text(f'TEST_API_KEY = "{secret_val}"\n')

    # 2. Nested sqlite database inside tests/fixtures/db/
    import sqlite3
    db_dir = proj / "tests" / "fixtures" / "db"
    db_dir.mkdir(parents=True)
    conn = sqlite3.connect(str(db_dir / "test_store.sqlite"))
    conn.execute("CREATE TABLE t (id INT);")
    conn.commit()
    conn.close()

    # 3. Nested Unicode tag prompt inside tests/fixtures/prompts/
    prompt_dir = proj / "tests" / "fixtures" / "prompts"
    prompt_dir.mkdir(parents=True)
    tag_payload = "\U000E0050\U000E0057\U000E004E"  # 'PWN'
    (prompt_dir / "system_prompt").write_text(f"System instructions {tag_payload}\n", encoding="utf-8")

    ctx = ProjectContext(project_path=proj)
    report = run_all_checks(ctx)

    assert report.has_failures, "Nested fixtures must not bypass security checks"
    # S01 detected secret in nested fixture
    assert report.results["S01"].verdict == Verdict.FAIL
    assert any("secret_fixture.py" in (f.path or "") for f in report.results["S01"].findings)

    # S02 detected sqlite database in nested fixture
    assert report.results["S02"].verdict == Verdict.FAIL
    assert any("test_store.sqlite" in (f.path or "") for f in report.results["S02"].findings)

    # A02 detected Unicode tag injection in extensionless prompt file
    assert report.results["A02"].verdict == Verdict.FAIL
    assert any("system_prompt" in (f.path or "") for f in report.results["A02"].findings)


def test_scan_limits_max_file_count_fails_safely(tmp_path: Path):
    """Resource bounds: Prove that exceeding MAX_FILE_COUNT (500) fails closed with an explicit error."""
    proj = tmp_path / "tools" / "bloated-tool"
    proj.mkdir(parents=True)
    (proj / "README.md").write_text("# Bloated Tool\n## Overview\nValid\n## License\nMIT\n")
    (proj / ".env.example").write_text("API_KEY=placeholder\n")
    (proj / ".gitignore").write_text(".venv/\n")
    (proj / "requirements.txt").write_text("pytest\n")

    # Generate 505 small files
    files_dir = proj / "generated"
    files_dir.mkdir()
    for i in range(505):
        (files_dir / f"file_{i:04d}.txt").write_text(f"content {i}\n")

    ctx = ProjectContext(project_path=proj)
    report = run_all_checks(ctx)

    # Must fail closed with F01 error, not report a clean pass
    assert report.has_failures, "Projects exceeding MAX_FILE_COUNT must fail validation"
    assert report.results["F01"].verdict == Verdict.FAIL
    assert any("maximum allowed file count" in f.message for f in report.results["F01"].findings)
    assert report.exit_code() == 1


def test_scan_limits_oversized_file_fails_safely(tmp_path: Path):
    """Resource bounds: Prove that exceeding MAX_FILE_SIZE (5 MB) fails closed with an explicit error."""
    proj = tmp_path / "tools" / "oversized-tool"
    proj.mkdir(parents=True)
    (proj / "README.md").write_text("# Oversized Tool\n## Overview\nValid\n## License\nMIT\n")
    (proj / ".env.example").write_text("API_KEY=placeholder\n")
    (proj / ".gitignore").write_text(".venv/\n")
    (proj / "requirements.txt").write_text("pytest\n")

    # Create 5 MB + 1024 bytes oversized file
    oversized_file = proj / "large_model.bin"
    with open(oversized_file, "wb") as f:
        f.seek((5 * 1024 * 1024) + 1024)
        f.write(b"\0")

    ctx = ProjectContext(project_path=proj)
    report = run_all_checks(ctx)

    assert report.has_failures, "Oversized files must fail validation"
    assert report.results["F01"].verdict == Verdict.FAIL
    assert any("exceeds the maximum allowed file size" in f.message for f in report.results["F01"].findings)
    assert any("large_model.bin" in (f.path or "") for f in report.results["F01"].findings)
    assert report.exit_code() == 1


def test_symlink_traversal_fails_safely(tmp_path: Path):
    """Path traversal: Prove that external symlinks fail closed with an explicit security error."""
    proj = tmp_path / "tools" / "symlink-tool"
    proj.mkdir(parents=True)
    (proj / "README.md").write_text("# Symlink Tool\n## Overview\nValid\n## License\nMIT\n")
    (proj / ".env.example").write_text("API_KEY=placeholder\n")
    (proj / ".gitignore").write_text(".venv/\n")
    (proj / "requirements.txt").write_text("pytest\n")

    # Target file outside the project boundary
    external_target = tmp_path / "external_secret.txt"
    external_target.write_text("TOP_SECRET_DATA\n")

    # Create symlink pointing outside
    symlink_path = proj / "escaped_link.txt"
    try:
        symlink_path.symlink_to(external_target)
    except OSError:
        pytest.skip("Symlink creation not permitted on this host OS without elevated privileges.")

    ctx = ProjectContext(project_path=proj)
    report = run_all_checks(ctx)

    assert report.has_failures, "External symlinks must trigger security failure"
    assert report.results["F01"].verdict == Verdict.FAIL
    assert any("resolves to external path" in f.message for f in report.results["F01"].findings)


def test_symlink_rejection_f01_logic(tmp_path: Path):
    """Path traversal: Verify that rejected symlinks recorded in ctx trigger explicit F01 failure."""
    proj = tmp_path / "tools" / "symlink-unit-tool"
    proj.mkdir(parents=True)
    (proj / "README.md").write_text("# Symlink Unit Tool\n## Overview\nValid\n## License\nMIT\n")
    (proj / ".env.example").write_text("API_KEY=placeholder\n")
    (proj / ".gitignore").write_text(".venv/\n")
    (proj / "requirements.txt").write_text("pytest\n")

    ctx = ProjectContext(project_path=proj)
    ctx.rejected_symlinks.append(("malicious_link.txt", "C:/Windows/System32/drivers/etc/hosts"))
    res = check_f01(ctx, {})
    assert res.verdict == Verdict.FAIL
    assert any("resolves to external path" in f.message for f in res.findings)
    assert any("malicious_link.txt" in (f.path or "") for f in res.findings)


def test_real_environment_file_variants(tmp_path: Path):
    """S01: Prove that all real environment file variants are caught while .env.example passes."""
    env_names = [".env", ".env.local", ".env.staging", ".env.test", ".env.production", "custom.env"]
    for name in env_names:
        proj = tmp_path / "tools" / f"env-{name.replace('.', '-')}"
        proj.mkdir(parents=True)
        (proj / "README.md").write_text("# Env Test\n## Overview\nValid\n## License\nMIT\n")
        (proj / ".env.example").write_text("API_KEY=placeholder\n")
        (proj / ".gitignore").write_text(".venv/\n")
        (proj / "requirements.txt").write_text("pytest\n")
        (proj / name).write_text("SECRET_KEY=12345\n")

        ctx = ProjectContext(project_path=proj)
        report = run_all_checks(ctx)
        assert report.results["S01"].verdict == Verdict.FAIL, f"Real env file '{name}' was not detected by S01!"
        assert any(name in (f.path or "") for f in report.results["S01"].findings)


def test_unexpected_exception_in_each_scanner(monkeypatch):
    """Fail-safe: Verify that an unexpected exception in each rule marks Verdict.ERROR, redacts secrets, and exits 2."""
    secret_to_leak = "AIza" + "Sy" + "TestLeakedKey123456789012345678"
    for target_rule_id, orig_fn in list(CHECK_REGISTRY):
        def crashing_fn(ctx, config, rid=target_rule_id):
            raise RuntimeError(f"Crashing rule {rid} with secret {secret_to_leak}")

        # Monkeypatch the registry item
        new_registry = [(r, crashing_fn if r == target_rule_id else fn) for r, fn in CHECK_REGISTRY]
        monkeypatch.setattr("merge_ready.checks.CHECK_REGISTRY", new_registry)

        ctx = ProjectContext(project_path=FIXTURES_DIR / "good-tool")
        report = run_all_checks(ctx)

        res = report.results[target_rule_id]
        assert res.verdict == Verdict.ERROR, f"Rule {target_rule_id} did not produce Verdict.ERROR on exception!"
        assert report.has_execution_errors, f"Report failed to flag execution errors for rule {target_rule_id}!"
        assert report.final_verdict == Verdict.ERROR, f"Overall verdict was not ERROR for rule {target_rule_id}!"
        assert report.exit_code() == 2, f"Exit code was not 2 for rule {target_rule_id} exception!"

        # Verify secret redaction in exception diagnostic
        for f in res.findings:
            assert secret_to_leak not in f.message
            assert "[REDACTED]" in f.message or "Crashing rule" in f.message


def test_unreadable_file_fails_safely(tmp_path: Path):
    """I/O bounds: Verify that unreadable or unscannable files trigger F01 failure and block PASS."""
    proj = tmp_path / "tools" / "unreadable-tool"
    proj.mkdir(parents=True)
    (proj / "README.md").write_text("# Unreadable Tool\n## Overview\nValid\n## License\nMIT\n")
    (proj / ".env.example").write_text("API_KEY=placeholder\n")
    (proj / ".gitignore").write_text(".venv/\n")
    (proj / "requirements.txt").write_text("pytest\n")

    ctx = ProjectContext(project_path=proj)
    ctx.unreadable_files.append(("locked_data.bin", "Permission denied: unable to stat"))

    res = check_f01(ctx, {})
    assert res.verdict == Verdict.FAIL
    assert any("could not be inspected" in f.message for f in res.findings)

    report = run_all_checks(ctx)
    assert report.has_failures
    assert report.final_verdict == Verdict.FAIL
    assert report.exit_code() == 1


def test_required_check_skipped_or_na_fails(monkeypatch):
    """Enforcement: Required checks marked SKIP or N/A must be converted to ERROR and block PASS."""
    for req_rule_id in REQUIRED_RULES:
        def skipping_fn(ctx, config, rid=req_rule_id):
            return RuleResult(rule_id=rid, name=f"Name {rid}", verdict=Verdict.SKIP, reason="attempted bypass")

        new_registry = [(r, skipping_fn if r == req_rule_id else fn) for r, fn in CHECK_REGISTRY]
        monkeypatch.setattr("merge_ready.checks.CHECK_REGISTRY", new_registry)

        ctx = ProjectContext(project_path=FIXTURES_DIR / "good-tool")
        report = run_all_checks(ctx)

        res = report.results[req_rule_id]
        assert res.verdict == Verdict.ERROR, f"Required rule {req_rule_id} was allowed to remain SKIP!"
        assert report.final_verdict == Verdict.ERROR
        assert report.exit_code() == 2


def test_optional_check_without_reason_fails(monkeypatch):
    """Enforcement: Optional checks marked SKIP or N/A without a documented reason must fail with ERROR."""
    def blank_skip_fn(ctx, config):
        return RuleResult(rule_id="P01", name="Scope", verdict=Verdict.SKIP, reason="")

    new_registry = [(r, blank_skip_fn if r == "P01" else fn) for r, fn in CHECK_REGISTRY]
    monkeypatch.setattr("merge_ready.checks.CHECK_REGISTRY", new_registry)

    ctx = ProjectContext(project_path=FIXTURES_DIR / "good-tool")
    report = run_all_checks(ctx)

    assert report.results["P01"].verdict == Verdict.ERROR
    assert any("without an explicit documented reason" in f.message for f in report.results["P01"].findings)
    assert report.final_verdict == Verdict.ERROR
    assert report.exit_code() == 2


def test_invalid_configuration_fails(tmp_path: Path):
    """Configuration: Malformed TOML in rules.toml must trigger Verdict.ERROR and exit 2."""
    proj = tmp_path / "tools" / "bad-config-tool"
    proj.mkdir(parents=True)
    (proj / "README.md").write_text("# Bad Config Tool\n## Overview\nValid\n## License\nMIT\n")
    (proj / ".env.example").write_text("API_KEY=placeholder\n")
    (proj / ".gitignore").write_text(".venv/\n")
    (proj / "requirements.txt").write_text("pytest\n")
    (proj / "rules.toml").write_text("[rules\ninvalid toml syntax == [[[\n")

    ctx = ProjectContext(project_path=proj)
    assert len(ctx.config_errors) > 0, "Failed to capture TOML syntax error"

    report = run_all_checks(ctx)
    assert report.has_execution_errors
    assert report.final_verdict == Verdict.ERROR
    assert report.exit_code() == 2
    assert report.results["F01"].verdict == Verdict.ERROR


def test_malformed_rule_output_fails(monkeypatch):
    """Malformed output: Checks returning non-RuleResult or invalid verdict strings must be caught as ERROR."""
    # 1. Check returning None
    def none_fn(ctx, config):
        return None

    new_registry1 = [(r, none_fn if r == "L01" else fn) for r, fn in CHECK_REGISTRY]
    monkeypatch.setattr("merge_ready.checks.CHECK_REGISTRY", new_registry1)
    ctx1 = ProjectContext(project_path=FIXTURES_DIR / "good-tool")
    report1 = run_all_checks(ctx1)
    assert report1.results["L01"].verdict == Verdict.ERROR
    assert report1.final_verdict == Verdict.ERROR
    assert report1.exit_code() == 2

    # 2. Check returning a string instead of RuleResult
    def str_fn(ctx, config):
        return "PASS"

    new_registry2 = [(r, str_fn if r == "L01" else fn) for r, fn in CHECK_REGISTRY]
    monkeypatch.setattr("merge_ready.checks.CHECK_REGISTRY", new_registry2)
    ctx2 = ProjectContext(project_path=FIXTURES_DIR / "good-tool")
    report2 = run_all_checks(ctx2)
    assert report2.results["L01"].verdict == Verdict.ERROR
    assert report2.exit_code() == 2

    # 3. Check returning an unrecognized verdict enum string
    def bad_verdict_fn(ctx, config):
        return RuleResult(rule_id="L01", name="Dedicated Location", verdict="TOTALLY_FINE")

    new_registry3 = [(r, bad_verdict_fn if r == "L01" else fn) for r, fn in CHECK_REGISTRY]
    monkeypatch.setattr("merge_ready.checks.CHECK_REGISTRY", new_registry3)
    ctx3 = ProjectContext(project_path=FIXTURES_DIR / "good-tool")
    report3 = run_all_checks(ctx3)
    assert report3.results["L01"].verdict == Verdict.ERROR
    assert report3.exit_code() == 2


def test_centralized_verdict_cannot_be_overridden():
    """Centralization: No individual rule or finding can override an overall FAIL or ERROR."""
    report = ValidationReport(project_path="tools/test", category="tools", slug="test")

    # Add a passing result
    report.add_result(RuleResult(rule_id="L01", name="Location", verdict=Verdict.PASS))
    assert report.final_verdict == Verdict.PASS
    assert report.exit_code() == 0

    # Add a failing result
    report.add_result(RuleResult(rule_id="S01", name="Secrets", verdict=Verdict.FAIL))
    assert report.final_verdict == Verdict.FAIL
    assert report.exit_code() == 1

    # Adding subsequent PASS results cannot revert the FAIL verdict
    report.add_result(RuleResult(rule_id="L02", name="Naming", verdict=Verdict.PASS))
    report.add_result(RuleResult(rule_id="F01", name="Files", verdict=Verdict.PASS))
    assert report.final_verdict == Verdict.FAIL
    assert report.exit_code() == 1

    # Adding an ERROR result escalates to Verdict.ERROR and exit code 2
    report.add_result(RuleResult(rule_id="D01", name="Template", verdict=Verdict.ERROR))
    assert report.final_verdict == Verdict.ERROR
    assert report.exit_code() == 2


def test_embedded_secret_redaction():
    """Verify that redact_secret redacts candidate API keys embedded in arbitrary text and exception traces."""
    # Synthetic harmless fragments (not a real key) without placeholder words like "fake"
    candidate_key = "AIza" + "Sy" + "CandidateSecretNotReal7890123456"
    raw_text = f"Connection failed while connecting with key={candidate_key} to endpoint https://example.com"
    redacted = redact_secret(raw_text)
    assert candidate_key not in redacted
    assert "[REDACTED]" in redacted
    assert "https://example.com" in redacted

    # Direct token test
    direct = redact_secret(candidate_key)
    assert candidate_key not in direct
    assert "[REDACTED]" in direct


def test_missing_required_rule_triggers_error(monkeypatch):
    """Fail-safe: If any required rule is missing from check execution, the report must mark it ERROR and exit 2."""
    # Simulate CHECK_REGISTRY missing S01
    filtered_registry = [(r, fn) for r, fn in CHECK_REGISTRY if r != "S01"]
    monkeypatch.setattr("merge_ready.checks.CHECK_REGISTRY", filtered_registry)

    ctx = ProjectContext(project_path=FIXTURES_DIR / "good-tool")
    report = run_all_checks(ctx)

    assert "S01" in report.results
    res = report.results["S01"]
    assert res.verdict == Verdict.ERROR
    assert any("Required check 'S01' was never executed" in f.message for f in res.findings)
    assert report.has_execution_errors
    assert report.final_verdict == Verdict.ERROR
    assert report.exit_code() == 2


def test_empty_report_cannot_pass():
    """Fail-safe: A ValidationReport with no results must never evaluate to PASS or exit 0."""
    report = ValidationReport(project_path="tools/empty-tool", category="tools", slug="empty-tool")
    assert len(report.results) == 0
    assert report.has_execution_errors is True
    assert report.final_verdict == Verdict.ERROR
    assert report.exit_code() == 2




