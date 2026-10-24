"""Abstract Syntax Tree (AST) safety validator for autonomous code patches."""

import ast
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

DISALLOWED_CALLS = {"eval", "exec", "__import__"}
DISALLOWED_ATTR_CALLS = {
    ("os", "system"),
    ("os", "popen"),
    ("os", "remove"),
    ("os", "unlink"),
    ("shutil", "rmtree"),
    ("subprocess", "call"),
    ("subprocess", "Popen"),
    ("subprocess", "run"),
    ("subprocess", "check_output"),
}


def validate_code_safety(code_str: str) -> Tuple[bool, str]:
    """Validates that proposed Python code is syntactically sound and free of destructive calls.

    Args:
        code_str: Python source code string.

    Returns:
        Tuple of (is_safe: bool, reason: str).
    """
    if not code_str or not code_str.strip():
        return False, "Code string is empty."

    try:
        tree = ast.parse(code_str)
    except SyntaxError as e:
        logger.warning(f"AST validation failed with SyntaxError: {e}")
        return False, f"Syntax error in code: {e.msg} (line {e.lineno})"

    # Traverse AST to inspect Call nodes
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Check simple function calls like eval(...)
            if isinstance(node.func, ast.Name) and node.func.id in DISALLOWED_CALLS:
                logger.warning(f"Blocked disallowed call: {node.func.id}()")
                return False, f"Blocked unsafe execution call: '{node.func.id}()' is prohibited."

            # Check attribute calls like os.system(...)
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                module_name = node.func.value.id
                attr_name = node.func.attr
                if (module_name, attr_name) in DISALLOWED_ATTR_CALLS:
                    logger.warning(f"Blocked disallowed attribute call: {module_name}.{attr_name}()")
                    return False, f"Blocked unsafe destructive call: '{module_name}.{attr_name}()'."

    return True, "AST analysis passed: syntax valid and security checks cleared."
