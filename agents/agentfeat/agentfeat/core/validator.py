"""Code validator: syntax verification, security boundaries, and secret detection."""

import ast
import json
import re
from pathlib import Path
from typing import List, Optional, Tuple

from agentfeat.models.schemas import FileChange
from agentfeat.utils.file_ops import is_path_safe

# Common patterns for committed secrets/keys
SECRET_PATTERNS = [
    (re.compile(r"AIzaSy[A-Za-z0-9_-]{20,}"), "Google API Key detected"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "OpenAI API Key detected"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "GitHub Personal Access Token detected"),
    (re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"), "Private Key detected"),
]


class CodeValidator:
    """Validates syntax and safety of generated code changes before disk writes."""

    @classmethod
    def validate_change(
        cls,
        change: FileChange,
        target_root: Optional[Path] = None,
    ) -> Tuple[bool, str]:
        """Validate a single FileChange for syntax, safety, and credentials.

        Returns:
            (is_valid, error_message)
        """
        # 1. Path Safety & Protected Files Check
        root = target_root or Path.cwd()
        safe_path, path_err = is_path_safe(root, change.file_path)
        if not safe_path:
            return False, f"Security Violation: {path_err}"

        if change.action == "delete":
            return True, ""

        if not change.new_content.strip():
            return False, "Generated file content is empty"

        # 2. Secret Pattern Scanning
        for pattern, desc in SECRET_PATTERNS:
            if pattern.search(change.new_content):
                return False, f"Security Violation: Hardcoded secret ({desc})"

        # 3. Syntax Verification
        ext = Path(change.file_path).suffix.lower()

        # Python syntax validation via AST
        if ext == ".py":
            try:
                ast.parse(change.new_content, filename=change.file_path)
            except SyntaxError as e:
                return False, f"Python SyntaxError at line {e.lineno}: {e.msg}"

        # JSON syntax validation
        elif ext == ".json":
            try:
                json.loads(change.new_content)
            except json.JSONDecodeError as e:
                return False, f"JSON SyntaxError at line {e.lineno}: {e.msg}"

        return True, ""

    @classmethod
    def validate_all(
        cls,
        changes: List[FileChange],
        target_root: Optional[Path] = None,
    ) -> bool:
        """Validate a batch of changes and update their status in-place.

        Returns True if all changes passed validation.
        """
        all_passed = True
        for change in changes:
            is_valid, error = cls.validate_change(change, target_root=target_root)
            change.is_valid = is_valid
            change.validation_error = error if not is_valid else None
            if not is_valid:
                all_passed = False
        return all_passed
