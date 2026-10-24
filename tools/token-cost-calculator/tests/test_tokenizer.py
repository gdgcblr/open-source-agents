"""Unit tests for token counter."""

import pytest
from calculator.tokenizer import count_tokens


def test_count_empty_text():
    assert count_tokens("") == 0
    assert count_tokens(None) == 0


def test_count_simple_sentence():
    count = count_tokens("Hello world, this is a token test.")
    assert 5 <= count <= 12


def test_count_longer_paragraph():
    paragraph = "Machine learning models process tokens rather than raw text. " * 10
    count = count_tokens(paragraph)
    assert count > 40
