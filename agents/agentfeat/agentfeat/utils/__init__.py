"""Utilities for file management, backups, diffing, and security."""

from .file_ops import (
    apply_file_changes,
    create_backup,
    generate_diff,
    get_file_tree,
    is_path_safe,
    read_file_safe,
    resolve_safe_path,
    restore_backup,
    write_file_safe,
)

__all__ = [
    "apply_file_changes",
    "create_backup",
    "generate_diff",
    "get_file_tree",
    "is_path_safe",
    "read_file_safe",
    "resolve_safe_path",
    "restore_backup",
    "write_file_safe",
]
