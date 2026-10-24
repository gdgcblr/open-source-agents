from pathlib import Path

from file_tools import read_source_file


def test_reads_supported_source_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("sample.py").write_text("print('hello')\n", encoding="utf-8")

    result = read_source_file("sample.py")

    assert result["status"] == "success"
    assert result["file_name"] == "sample.py"
    assert result["language"] == "py"
    assert result["content"] == "print('hello')\n"
    assert result["line_count"] == 1


def test_rejects_absolute_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = read_source_file(str((tmp_path / "sample.py").resolve()))

    assert result["status"] == "error"


def test_rejects_path_traversal(tmp_path, monkeypatch):
    outside = tmp_path.parent / "outside.py"
    outside.write_text("print('outside')", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = read_source_file("../outside.py")

    assert result["status"] == "error"


def test_rejects_hidden_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path(".env").write_text("GOOGLE_API_KEY=not-a-real-key", encoding="utf-8")

    result = read_source_file(".env")

    assert result["status"] == "error"


def test_rejects_unsupported_extension(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("notes.txt").write_text("not source code", encoding="utf-8")

    result = read_source_file("notes.txt")

    assert result["status"] == "error"


def test_rejects_oversized_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("large.py").write_text("x" * 100_001, encoding="utf-8")

    result = read_source_file("large.py")

    assert result["status"] == "error"
