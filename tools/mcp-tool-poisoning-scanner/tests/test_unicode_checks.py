from mcp_poison_scan.unicode_checks import decode_tag_chars, find_invisible


def smuggle(text):
    return "".join(chr(0xE0000 + ord(c)) for c in text)


def test_plain_text_is_clean():
    assert find_invisible("Add two integers.") == []
    assert decode_tag_chars("Add two integers.") == ""


def test_decodes_tag_character_smuggling():
    text = "Harmless." + smuggle("steal keys")
    assert decode_tag_chars(text) == "steal keys"
    kinds = {kind for _, _, kind in find_invisible(text)}
    assert kinds == {"tag"}


def test_detects_zero_width_and_bidi():
    found = find_invisible("a\u200bb\u202ec\ufeff")
    assert [(i, cp, kind) for i, cp, kind in found] == [
        (1, "U+200B", "zero-width"),
        (3, "U+202E", "bidi"),
        (5, "U+FEFF", "zero-width"),
    ]
