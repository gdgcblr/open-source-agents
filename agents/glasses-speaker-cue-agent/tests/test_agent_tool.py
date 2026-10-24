from types import SimpleNamespace

from glasses_speaker_cue_agent.agent import estimate_speaking_time
from glasses_speaker_cue_agent.config import MAX_REVISIONS


def _context():
    return SimpleNamespace(state={})


def test_reports_fit_and_word_change():
    ctx = _context()
    result = estimate_speaking_time(" ".join(["word"] * 300), 60, ctx)
    assert result["measured_seconds"] == 120
    assert result["fits"] is False
    assert result["word_change_needed"] == -150


def test_revision_count_is_session_scoped_so_it_survives_the_retry_turn():
    ctx = _context()
    estimate_speaking_time("word", 60, ctx)
    assert ctx.state
    assert not any(key.startswith("temp:") for key in ctx.state)


def test_revision_cap_is_enforced_in_code():
    ctx = _context()
    long_script = " ".join(["word"] * 300)
    results = [estimate_speaking_time(long_script, 60, ctx) for _ in range(MAX_REVISIONS + 2)]
    assert [r["revisions_left"] for r in results[: MAX_REVISIONS + 1]] == list(
        range(MAX_REVISIONS, -1, -1)
    )
    assert results[-1]["revisions_left"] == 0
    assert "Stop revising" in results[-1]["next_step"]
