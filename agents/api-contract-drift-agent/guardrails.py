import json
import re
from pathlib import Path
from typing import List, Tuple

MAX_FILE_SIZE_BYTES = 256 * 1024  # 256 KB max limit per file

SECRET_PATTERNS = [
    (r"(?i)api[_-]?key\s*[:=]\s*['\"][a-zA-Z0-9_\-]{16,}['\"]", "API Key"),
    (r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{20,}", "Bearer Token"),
    (r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----", "Private Key"),
    (r"(?i)password\s*[:=]\s*['\"][^'\"]{6,}['\"]", "Hardcoded Password"),
    (r"(?i)aws[_-]?secret[_-]?access[_-]?key\s*[:=]\s*['\"][a-zA-Z0-9/+=]{40}['\"]", "AWS Secret Key"),
]

INJECTION_PATTERNS = [
    r"(?i)ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"(?i)you\s+are\s+now\s+in\s+debug\s+mode",
    r"(?i)override\s+system\s+prompt",
    r"(?i)mark\s+all\s+(as\s+)?compliant",
]


class GuardrailValidationError(Exception):
    """Raised when an input or output fails security guardrails."""
    pass


def validate_file_path(target_path: Path) -> Path:
    resolved_path = target_path.resolve()
    if not resolved_path.is_file():
        raise GuardrailValidationError(f"Target path does not exist or is not a file: {target_path}")
    
    if resolved_path.stat().st_size > MAX_FILE_SIZE_BYTES:
        raise GuardrailValidationError(
            f"File {target_path.name} exceeds size limit ({resolved_path.stat().st_size} > {MAX_FILE_SIZE_BYTES} bytes)"
        )
    return resolved_path


def scan_for_secrets(content: str, filename: str) -> List[str]:
    detected = []
    for pattern, name in SECRET_PATTERNS:
        if re.search(pattern, content):
            detected.append(f"Potential {name} detected in {filename}")
    return detected


def scan_for_prompt_injection(content: str) -> None:
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, content):
            raise GuardrailValidationError(
                f"Security Guardrail Triggered: Potential prompt injection sequence detected: {pattern}"
            )


def validate_patch_output(patch_str: str) -> Tuple[bool, str]:
    if not patch_str or not patch_str.strip():
        return True, "No patch generated."
    
    clean_patch = patch_str.strip()
    if clean_patch.startswith("```json"):
        clean_patch = clean_patch[7:]
    if clean_patch.startswith("```"):
        clean_patch = clean_patch[3:]
    if clean_patch.endswith("```"):
        clean_patch = clean_patch[:-3]
    clean_patch = clean_patch.strip()

    try:
        json.loads(clean_patch)
        return True, "Valid JSON OpenAPI patch."
    except json.JSONDecodeError:
        if ":" in clean_patch:
            return True, "Valid YAML-like structural patch."
        return False, "Generated patch failed structural validation (invalid JSON/YAML syntax)."