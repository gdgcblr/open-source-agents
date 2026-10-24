"""Deterministic offline mock healer engine for zero-key test verification."""

import re


class MockHealerEngine:
    """Simulates Gemini code healing patches for testing and evaluation."""

    def heal_code(self, file_path: str, current_code: str, test_failure: str) -> str:
        """Generates a corrected version of the code resolving common simulated bugs."""
        # Handle demo bug: division by zero or off-by-one in calculator
        if "ZeroDivisionError" in test_failure or "def divide" in current_code:
            # Fix divide to handle zero safely
            fixed = re.sub(
                r"def divide\(a, b\):.*?(?=\ndef|\Z)",
                "def divide(a, b):\n    if b == 0:\n        raise ValueError(\"Cannot divide by zero\")\n    return a / b\n",
                current_code,
                flags=re.DOTALL
            )
            # Fix off-by-one in multiply/add if present
            fixed = fixed.replace("return a + b + 1", "return a + b")
            fixed = fixed.replace("return a * b * 2", "return a * b")
            return fixed

        # General fix: replace failing assertions or syntax issues
        if "assert" in test_failure:
            fixed = current_code.replace("return False", "return True")
            fixed = fixed.replace("return -1", "return 0")
            return fixed

        return current_code
