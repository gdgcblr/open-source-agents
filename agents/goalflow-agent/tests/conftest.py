"""Pytest configuration and fixtures for GoalFlow tests."""

import os
import tempfile
import pytest
from goalflow import db


@pytest.fixture
def temp_db(tmp_path):
    """Provide a fresh, isolated SQLite database for each test."""
    db_file = tmp_path / "test_goalflow.db"
    db_path = str(db_file)
    db.init_db(db_path=db_path)
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)
