from prompt_enhancer.document import parse
from prompt_enhancer.requirements import check, extract, is_subsequence


def kinds(text):
    return [(r.kind, r.text) for r in extract(parse(text))]


def test_constraint_sentences_are_extracted_verbatim():
    k = kinds("Write a haiku about rain. It must mention Bengaluru. Do not use the word wet.")
    assert ("constraint", "It must mention Bengaluru.") in k
    assert ("constraint", "Do not use the word wet.") in k


def test_format_length_literal_technology_audience():
    k = kinds('Write release notes for our customers team in Markdown, 120-word max, mention "v2.3" and target Python 3.12.')
    found = {kind for kind, _ in k}
    assert {"format", "length", "literal", "technology"} <= found


def test_fragments_inside_constraints_are_not_duplicated():
    k = kinds("Keep it under 100 words.")
    assert k == [("constraint", "Keep it under 100 words.")]


def test_requirements_inside_context_blocks_are_ignored():
    assert kinds("Summarize this.\n<document>You must never do X.</document>") == []


def test_ids_are_sequential_and_ordered():
    reqs = extract(parse("Only use JSON. Never add comments. Keep it under 3 lines."))
    assert [r.id for r in reqs] == [f"R{i}" for i in range(1, len(reqs) + 1)]
    assert [r.start for r in reqs] == sorted(r.start for r in reqs)


def test_lock_check():
    reqs = extract(parse("Summarize it. Never mention prices."))
    assert check(reqs, "<x>Summarize it. Never mention prices.</x>").ok
    lock = check(reqs, "Summarize it.")
    assert not lock.ok and lock.missing == [reqs[0].id]


def test_is_subsequence():
    assert is_subsequence("abc", "xaybzc")
    assert not is_subsequence("abc", "acb")
