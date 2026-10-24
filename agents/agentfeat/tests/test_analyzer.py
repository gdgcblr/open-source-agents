"""Tests for CodebaseAnalyzer."""

import pytest
from pathlib import Path
from agentfeat.core.analyzer import CodebaseAnalyzer


def test_codebase_analyzer_basic(tmp_path: Path):
    # Setup mock repo structure
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hello world')", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("fastapi==0.100.0\npytest\n", encoding="utf-8")

    analyzer = CodebaseAnalyzer(tmp_path)
    summary = analyzer.analyze("Add authentication")

    assert summary.total_files >= 2
    assert "Python" in summary.languages
    assert "FastAPI" in summary.frameworks
    assert "requirements.txt" in summary.manifest_files
    assert len(summary.relevant_files) > 0


def test_codebase_analyzer_ignore_dirs(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("dummy", encoding="utf-8")
    (tmp_path / "main.py").write_text("def main(): pass", encoding="utf-8")

    analyzer = CodebaseAnalyzer(tmp_path)
    summary = analyzer.analyze()

    assert ".git" not in summary.file_tree
    assert summary.total_files == 1
