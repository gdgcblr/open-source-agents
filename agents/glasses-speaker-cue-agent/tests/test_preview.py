from glasses_preview import LENS_TEXT_WIDTH, load_cards, render

DECK = {
    "cues": [
        {
            "index": 0,
            "heading": "Hook",
            "text": "Speakers lose their place when they look down at a laptop.",
            "sayByLabel": "4s",
            "flags": [],
        },
        {
            "index": 1,
            "heading": "Fix",
            "text": "Cues in your glasses.",
            "sayByLabel": "6s",
            "flags": ["number not in notes: 40"],
        },
    ],
    "qa": [{"question": "Needs glasses?", "answer": "No."}],
}


def test_cards_cover_cues_then_qa():
    cards = load_cards(DECK)
    assert [c.header for c in cards] == ["Hook  1/2", "Fix  2/2", "Q&A  1/1"]
    assert cards[1].footer.endswith("⚠")


def test_render_keeps_every_line_inside_the_lens():
    box = render(load_cards(DECK)[0])
    widths = {len(line) for line in box.splitlines()}
    assert widths == {LENS_TEXT_WIDTH + 4}


def test_long_heading_is_shortened_but_counter_kept():
    deck = {"cues": [{**DECK["cues"][0], "heading": "Why Agents Fail Today In Production"}]}
    deck["cues"] = deck["cues"] * 40
    card = load_cards(deck)[0]
    assert len(card.header) <= LENS_TEXT_WIDTH
    assert card.header.endswith("1/40")
    assert {len(line) for line in render(card).splitlines()} == {LENS_TEXT_WIDTH + 4}
