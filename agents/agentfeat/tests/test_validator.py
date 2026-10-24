"""Tests for CodeValidator."""

from agentfeat.core.validator import CodeValidator
from agentfeat.models.schemas import FileChange


def test_validator_valid_python():
    change = FileChange(
        file_path="service.py",
        action="create",
        description="test",
        new_content="def hello() -> str:\n    return 'world'\n",
    )
    is_valid, err = CodeValidator.validate_change(change)
    assert is_valid is True
    assert err == ""


def test_validator_invalid_python_syntax():
    change = FileChange(
        file_path="broken.py",
        action="create",
        description="test",
        new_content="def bad_syntax(:\n    pass\n",
    )
    is_valid, err = CodeValidator.validate_change(change)
    assert is_valid is False
    assert "SyntaxError" in err


def test_validator_valid_json():
    change = FileChange(
        file_path="config.json",
        action="create",
        description="test",
        new_content='{"key": "value"}',
    )
    is_valid, err = CodeValidator.validate_change(change)
    assert is_valid is True


def test_validator_invalid_json():
    change = FileChange(
        file_path="broken.json",
        action="create",
        description="test",
        new_content='{"unclosed": ',
    )
    is_valid, err = CodeValidator.validate_change(change)
    assert is_valid is False
