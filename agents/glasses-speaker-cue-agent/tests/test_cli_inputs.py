import pytest

from glasses_speaker_cue_agent.config import MAX_IMAGE_BYTES
from main import EXIT_BAD_INPUT, main


@pytest.fixture(autouse=True)
def _no_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-used")


def test_directory_as_notes_is_a_clean_input_error(tmp_path, capsys):
    assert main(["--notes", str(tmp_path)]) == EXIT_BAD_INPUT
    assert "Cannot read notes file" in capsys.readouterr().err


def test_non_utf8_notes_are_a_clean_input_error(tmp_path, capsys):
    notes = tmp_path / "notes.txt"
    notes.write_bytes("café".encode("latin-1"))
    assert main(["--notes", str(notes)]) == EXIT_BAD_INPUT
    assert "not UTF-8" in capsys.readouterr().err


def test_oversized_slide_is_rejected_before_reading(tmp_path, capsys):
    notes = tmp_path / "notes.txt"
    notes.write_text("hello", encoding="utf-8")
    slide = tmp_path / "huge.png"
    with slide.open("wb") as f:
        f.truncate(MAX_IMAGE_BYTES + 1)  # sparse: no real data is written
    assert main(["--notes", str(notes), "--slide", str(slide)]) == EXIT_BAD_INPUT
    assert "larger than" in capsys.readouterr().err
