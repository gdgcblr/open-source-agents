
import pytest

from code_reader import read_source_file, split_code


def test_read_source_file(tmp_path):
    source = tmp_path / "example.py"
    source.write_text("def hello():\n    return 'hi'\n", encoding="utf-8")

    assert "def hello()" in read_source_file(str(source))


def test_missing_file():
    with pytest.raises(FileNotFoundError):
        read_source_file("does-not-exist.py")


def test_unsupported_file(tmp_path):
    source = tmp_path / "notes.txt"
    source.write_text("hello", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported"):
        read_source_file(str(source))


def test_split_code():
    chunks = split_code("line 1\nline 2\nline 3", max_lines=2)

    assert chunks == ["line 1\nline 2", "line 3"]


def test_split_empty_code():
    assert split_code("") == []


def test_invalid_chunk_size():
    with pytest.raises(ValueError):
        split_code("hello", max_lines=0)
