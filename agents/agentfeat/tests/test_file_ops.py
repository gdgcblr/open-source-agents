"""Tests for file operations and diffing."""

from pathlib import Path
from agentfeat.models.schemas import FileChange
from agentfeat.utils.file_ops import (
    apply_file_changes,
    create_backup,
    generate_diff,
    get_file_tree,
    read_file_safe,
    write_file_safe,
)


def test_write_and_read_safe(tmp_path: Path):
    target = tmp_path / "subdir" / "sample.txt"
    write_file_safe(target, "Hello AgentFeat")

    content, truncated = read_file_safe(target)
    assert content == "Hello AgentFeat"
    assert truncated is False


def test_generate_diff():
    orig = "line1\nline2\n"
    modified = "line1\nline2 modified\nline3\n"
    diff = generate_diff(orig, modified, "sample.txt")

    assert "-line2" in diff
    assert "+line2 modified" in diff
    assert "+line3" in diff


def test_backup_and_apply_changes(tmp_path: Path):
    f1 = tmp_path / "hello.py"
    f1.write_text("initial = True\n", encoding="utf-8")

    changes = [
        FileChange(
            file_path="hello.py",
            action="modify",
            description="updated",
            new_content="initial = False\n",
        ),
        FileChange(
            file_path="new_module.py",
            action="create",
            description="added",
            new_content="# new\n",
        ),
    ]

    backup_dir = apply_file_changes(tmp_path, changes, create_backups=True)
    assert backup_dir is not None
    assert (backup_dir / "hello.py").exists()
    assert (backup_dir / "hello.py").read_text() == "initial = True\n"

    # Verify changes applied
    assert f1.read_text() == "initial = False\n"
    assert (tmp_path / "new_module.py").read_text() == "# new\n"


def test_file_tree(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text("export const x = 1;", encoding="utf-8")

    tree = get_file_tree(tmp_path)
    assert "src/" in tree
    assert "index.ts" in tree
