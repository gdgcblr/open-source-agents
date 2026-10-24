"""Detect characters that are invisible to humans but still read by LLMs."""

ZERO_WIDTH = {0x200B, 0x200C, 0x200D, 0x2060, 0x180E, 0xFEFF}
BIDI = set(range(0x202A, 0x202F)) | set(range(0x2066, 0x206A))
TAG_RANGE = range(0xE0000, 0xE0080)


def _kind(codepoint):
    if codepoint in TAG_RANGE:
        return "tag"
    if codepoint in ZERO_WIDTH:
        return "zero-width"
    if codepoint in BIDI:
        return "bidi"
    return None


def find_invisible(text):
    """Return [(index, "U+XXXX", kind)] for every hidden character in text."""
    found = []
    for index, char in enumerate(text):
        kind = _kind(ord(char))
        if kind:
            found.append((index, f"U+{ord(char):04X}", kind))
    return found


def decode_tag_chars(text):
    """Decode ASCII smuggled via Unicode tag characters (U+E0020-U+E007E)."""
    return "".join(
        chr(ord(char) - 0xE0000) for char in text if 0xE0020 <= ord(char) <= 0xE007E
    )
