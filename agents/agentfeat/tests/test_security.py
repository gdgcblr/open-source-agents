"""Security audit and boundary tests for AgentFeat."""

from pathlib import Path
import pytest

from agentfeat.core.validator import CodeValidator
from agentfeat.models.schemas import FileChange
from agentfeat.utils.file_ops import (
    apply_file_changes,
    is_path_safe,
    resolve_safe_path,
    restore_backup,
)


def test_path_traversal_detection(tmp_path: Path):
    # Traversal via parent directory
    is_safe, err = is_path_safe(tmp_path, "../../etc/passwd")
    assert is_safe is False
    assert "Directory traversal" in err

    # Absolute path
    is_safe, err = is_path_safe(tmp_path, "/etc/shadow")
    assert is_safe is False
    assert "Absolute paths are forbidden" in err


def test_resolve_safe_path_raises_on_traversal(tmp_path: Path):
    with pytest.raises(PermissionError):
        resolve_safe_path(tmp_path, "../outside.txt")


def test_protected_files_blocked(tmp_path: Path):
    # .env files
    is_safe, err = is_path_safe(tmp_path, ".env")
    assert is_safe is False
    assert "protected sensitive pattern" in err

    is_safe, err = is_path_safe(tmp_path, "sub/.env.local")
    assert is_safe is False

    # Git directory
    is_safe, err = is_path_safe(tmp_path, ".git/config")
    assert is_safe is False

    # Private keys
    is_safe, err = is_path_safe(tmp_path, "id_rsa")
    assert is_safe is False

    is_safe, err = is_path_safe(tmp_path, "server.key")
    assert is_safe is False


def test_validator_detects_secrets():
    change = FileChange(
        file_path="config.py",
        action="create",
        description="add key",
        new_content='API_KEY = "AIzaSyDummyKeyForTestingOnly1234567890"',
    )
    is_valid, err = CodeValidator.validate_change(change)
    assert is_valid is False
    assert "Hardcoded secret" in err


def test_validator_blocks_path_traversal_in_change(tmp_path: Path):
    change = FileChange(
        file_path="../escape.py",
        action="create",
        description="escape root",
        new_content="x = 1\n",
    )
    is_valid, err = CodeValidator.validate_change(change, target_root=tmp_path)
    assert is_valid is False
    assert "Security Violation" in err


def test_backup_and_restore_behavior(tmp_path: Path):
    original_file = tmp_path / "service.py"
    original_file.write_text("VERSION = '1.0.0'\n", encoding="utf-8")

    change = FileChange(
        file_path="service.py",
        action="modify",
        description="upgrade version",
        new_content="VERSION = '2.0.0'\n",
    )

    backup_dir = apply_file_changes(tmp_path, [change], create_backups=True)
    assert backup_dir is not None
    assert original_file.read_text() == "VERSION = '2.0.0'\n"

    # Restore backup
    restored = restore_backup(backup_dir, tmp_path)
    assert "service.py" in restored
    assert original_file.read_text() == "VERSION = '1.0.0'\n"
