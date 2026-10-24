"""Pytest suite for broken_math.py."""

import pytest
from broken_math import add, divide


def test_add():
    assert add(2, 3) == 5
    assert add(-1, 1) == 0


def test_divide():
    assert divide(10, 2) == 5.0
    with pytest.raises(ValueError):
        divide(5, 0)
