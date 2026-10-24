from glasses_speaker_cue_agent.duration import (
    estimate_seconds,
    format_seconds,
    say_by,
    target_words,
    word_count,
)


def test_word_count_ignores_punctuation_tokens():
    assert word_count("Agents fail — here's why, in 3 steps.") == 7


def test_word_count_handles_kannada_combining_marks():
    assert word_count("ಇದು ಕನ್ನಡ ವಾಕ್ಯ") == 3


def test_estimate_seconds_at_150_wpm():
    assert estimate_seconds(" ".join(["word"] * 150)) == 60
    assert estimate_seconds("") == 0
    assert estimate_seconds("Hi") == 1


def test_target_words():
    assert target_words(120) == 300


def test_say_by_is_cumulative():
    assert say_by([" ".join(["w"] * 75), " ".join(["w"] * 75)]) == [30, 60]


def test_format_seconds():
    assert format_seconds(45) == "45s"
    assert format_seconds(65) == "1:05"
    assert format_seconds(720) == "12:00"
