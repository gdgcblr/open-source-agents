from glasses_speaker_cue_agent.cues import (
    Section,
    body_from_sections,
    chunk,
    cues,
    sections_from_body,
)


def test_headings_start_sections():
    body = "## Hook\nAgents fail.\nHere's why.\n\n## Demo\nWatch this."
    assert sections_from_body(body) == [
        Section("Hook", "Agents fail. Here's why."),
        Section("Demo", "Watch this."),
    ]


def test_paragraphs_become_sections_without_headings():
    assert sections_from_body("First idea.\n\nSecond idea.") == [
        Section("", "First idea."),
        Section("", "Second idea."),
    ]


def test_body_round_trips_through_sections():
    sections = [Section("Hook", "Agents fail."), Section("Close", "Thanks!")]
    assert sections_from_body(body_from_sections(sections)) == sections


def test_short_sentences_are_packed_together():
    assert chunk("One. Two. Three.") == ["One. Two. Three."]


def test_every_chunk_fits_the_lens():
    text = (
        "This sentence is deliberately long, with several clauses, so that it has to be "
        "split across more than one cue on a small display; otherwise the speaker would "
        "have to read a paragraph off their glasses, which defeats the point entirely."
    )
    parts = chunk(text, max_chars=90)
    assert len(parts) > 1
    assert all(len(p) <= 90 for p in parts)
    assert " ".join(parts) == text


def test_kannada_text_is_split_within_limit():
    sentence = "ಇದು ಕನ್ನಡ ವಾಕ್ಯ. "
    parts = chunk(sentence * 12, max_chars=40)
    assert parts
    assert all(len(p) <= 40 for p in parts)


def test_hindi_danda_ends_a_sentence():
    assert chunk("पहला वाक्य। दूसरा वाक्य।", max_chars=15) == ["पहला वाक्य।", "दूसरा वाक्य।"]


def test_cues_are_numbered_across_sections_and_default_headings():
    result = cues([Section("", "Hello there."), Section("Close", "Bye.")])
    assert [(c.index, c.section_index, c.heading, c.text) for c in result] == [
        (0, 0, "Part 1", "Hello there."),
        (1, 1, "Close", "Bye."),
    ]


def test_empty_text_gives_no_chunks():
    assert chunk("   ") == []
