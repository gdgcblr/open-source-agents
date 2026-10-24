import json

import pytest

from glasses_speaker_cue_agent.config import MAX_CUE_CHARS
from glasses_speaker_cue_agent.deck import (
    DraftError,
    build_deck,
    parse_draft,
    to_script_markdown,
)

_DRAFT = {
    "title": "Why agents fail",
    "sections": [
        {
            "heading": "Hook",
            "spokenText": "Most agents fail in production. Here's why, and how to fix it.",
            "cueKeywords": ["fail"],
        },
        {
            "heading": "",
            "spokenText": "Give them tools that check their own work. "
            "That's the trick, and it's simple to add.",
            "cueKeywords": [],
        },
    ],
    "qa": [{"question": "Which framework?", "answer": "Google ADK.", "fromNotes": True}],
}
# Models often wrap JSON in a Markdown fence; the parser must cope.
REPLY = f"```json\n{json.dumps(_DRAFT, indent=2)}\n```"


def test_parse_draft_tolerates_code_fences():
    draft = parse_draft(REPLY)
    assert draft.title == "Why agents fail"
    assert len(draft.sections) == 2


@pytest.mark.parametrize("raw", ["no json here", '{"title": "x", "sections": []}', "{not json}"])
def test_parse_draft_rejects_unusable_replies(raw):
    with pytest.raises(DraftError):
        parse_draft(raw)


def test_deck_cues_fit_the_lens_and_are_timed_in_order():
    deck = build_deck(parse_draft(REPLY), target_seconds=10, language="English")
    assert all(len(c.text) <= MAX_CUE_CHARS for c in deck.cues)
    assert [c.sayBy for c in deck.cues] == sorted(c.sayBy for c in deck.cues)
    assert deck.sections[1].heading == "Part 2"
    assert deck.estimatedDurationSeconds > 0


def test_qa_is_capped_and_dropped_in_code():
    draft = parse_draft(REPLY)
    draft.qa = draft.qa * 5
    assert len(build_deck(draft, 10, "English").qa) == 3
    assert build_deck(draft, 10, "English", include_qa=False).qa == []


def test_deck_warns_when_outside_target():
    deck = build_deck(parse_draft(REPLY), target_seconds=600, language="English")
    assert not deck.fitsTarget
    assert deck.warnings


def test_script_markdown_has_headings_and_qa_section():
    md = to_script_markdown(build_deck(parse_draft(REPLY), 10, "English"))
    assert md.startswith("## Hook\n")
    assert "## Part 2\n" in md
    assert "## Q&A\nQ: Which framework?\nA: Google ADK." in md
