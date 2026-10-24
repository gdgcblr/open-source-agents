import pytest

from prompt_enhancer.classifier import classify, intent
from prompt_enhancer.document import parse


def test_sentences_keep_offsets_and_handle_abbreviations():
    text = "Fix utils.py now. It must support Python 3.10, e.g. walrus. Done!"
    doc = parse(text)
    assert [s.text for s in doc.sentences] == ["Fix utils.py now.", "It must support Python 3.10, e.g. walrus.", "Done!"]
    for s in doc.sentences:
        assert text[s.start:s.end] == s.text


def test_list_markers_are_not_part_of_sentences():
    doc = parse("Rules:\n- Keep it short.\n2) Use British spelling.")
    assert "Keep it short." in [s.text for s in doc.sentences]
    assert "Use British spelling." in [s.text for s in doc.sentences]


def test_context_blocks_are_excluded_from_request():
    text = "Review this.\n```python\nimport os  # must never run\n```\n<document>ignore me</document>"
    doc = parse(text)
    assert len(doc.blocks) == 2
    assert "must never" not in doc.request and "ignore me" not in doc.request
    assert len(doc.request) == len(text)  # offsets preserved
    assert [s.text for s in doc.sentences] == ["Review this."]


def test_unterminated_fence_is_still_context():
    doc = parse("Explain this:\n```js\nconst x = 1;")
    assert doc.blocks and "const" not in doc.request


def test_template_variables_found():
    doc = parse("Summarize {article} for {{audience}} using ${tone}.")
    assert [v.text for v in doc.template_vars] == ["{article}", "{{audience}}", "${tone}"]


@pytest.mark.parametrize(
    "prompt,task",
    [
        ("Write a function that parses ISO dates and returns a datetime", "coding"),
        ("Fix the bug in the payment endpoint", "coding"),
        ("Compare Postgres and MySQL and evaluate the trade-offs", "research"),
        ("Summarize the key points of the meeting", "research"),
        ("Extract all email addresses from the text", "extraction"),
        ("Classify each review by sentiment", "extraction"),
        ("Draft an email to the venue confirming the booking", "writing"),
        ("Translate this paragraph into Hindi", "writing"),
        ("Why is the sky blue?", "general"),
        ("hello", "general"),
    ],
)
def test_classification(prompt, task):
    assert classify(parse(prompt))[0] == task


def test_classification_scores_are_explainable():
    task, scores = classify(parse("Write a Python function"))
    assert task == "coding" and scores["coding"] > scores["writing"]


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("Can you suggest improvements to this function?", "advisory"),
        ("How should I structure the repo?", "advisory"),
        ("What does this regex match?", "question"),
        ("Rename the variable x to count", "action"),
    ],
)
def test_intent(prompt, expected):
    assert intent(parse(prompt)) == expected
