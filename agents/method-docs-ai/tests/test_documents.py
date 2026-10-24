import pytest
from knowflow.documents import chunk_text
from knowflow.indexer import lexical_score, tokenize


def test_chunk_text_empty():
    assert chunk_text("") == []


def test_chunk_text_splits_and_overlaps():
    text = "alpha " * 100
    chunks = chunk_text(text, chunk_size=100, overlap=20)
    assert len(chunks) > 1
    assert all(chunks)


def test_chunk_config_validation():
    with pytest.raises(ValueError):
        chunk_text("some text", chunk_size=10, overlap=10)


def test_tokenize_removes_common_words():
    assert tokenize("How do I configure OData collections?") == ["configure", "odata", "collections"]


def test_lexical_score_matches_relevant_text():
    query = tokenize("OData collection payload")
    relevant = tokenize("Configure OData collection payload values")
    unrelated = tokenize("Reset browser cache settings")
    assert lexical_score(query, relevant) > lexical_score(query, unrelated)


def test_lexical_score_empty_is_zero():
    assert lexical_score([], ["hello"]) == 0.0
