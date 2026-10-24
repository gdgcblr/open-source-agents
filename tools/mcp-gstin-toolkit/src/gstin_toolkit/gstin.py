"""GSTIN parsing and validation (format, state code, PAN, check digit)."""

import re
from dataclasses import asdict, dataclass, field

from .states import STATE_CODES

_CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]{3}$")

# 4th character of the PAN encodes the holder type.
PAN_HOLDER_TYPES = {
    "A": "Association of Persons",
    "B": "Body of Individuals",
    "C": "Company",
    "F": "Firm / LLP",
    "G": "Government",
    "H": "Hindu Undivided Family",
    "J": "Artificial Juridical Person",
    "L": "Local Authority",
    "P": "Individual",
    "T": "Trust",
}


@dataclass
class GstinResult:
    input: str
    gstin: str
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    state_code: str | None = None
    state: str | None = None
    pan: str | None = None
    pan_holder_type: str | None = None
    registration_number: str | None = None
    expected_check_digit: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def normalize(raw: str) -> str:
    """Uppercase and strip whitespace, dashes and dots that often creep into feeds."""
    return re.sub(r"[\s\-.]", "", str(raw or "")).upper()


def check_digit(first14: str) -> str:
    """Compute the 15th (check) character of a GSTIN from its first 14 characters."""
    total = 0
    for i, ch in enumerate(first14):
        product = _CHARSET.index(ch) * (2 if i % 2 else 1)
        total += product // 36 + product % 36
    return _CHARSET[(36 - total % 36) % 36]


def validate_gstin(raw: str) -> GstinResult:
    gstin = normalize(raw)
    result = GstinResult(input=str(raw), gstin=gstin, valid=False)

    if not gstin:
        result.errors.append("empty value")
        return result
    if len(gstin) != 15:
        result.errors.append(f"length is {len(gstin)}, expected 15")
        return result
    if not _PATTERN.match(gstin):
        result.errors.append("does not match GSTIN format (2 digits + PAN + entity + 'Z' + check)")
        return result

    result.state_code = gstin[:2]
    result.state = STATE_CODES.get(result.state_code)
    result.pan = gstin[2:12]
    result.pan_holder_type = PAN_HOLDER_TYPES.get(gstin[5])
    result.registration_number = gstin[12]
    result.expected_check_digit = check_digit(gstin[:14])

    if result.state is None:
        result.errors.append(f"unknown state code {result.state_code}")
    if result.registration_number == "0":
        result.errors.append("13th character (registration number) cannot be 0")
    if result.pan_holder_type is None:
        result.warnings.append(f"unusual PAN holder type '{gstin[5]}'")
    if gstin[13] != "Z":
        result.warnings.append(f"14th character is '{gstin[13]}', usually 'Z'")
    if gstin[14] != result.expected_check_digit:
        result.errors.append(
            f"check digit is '{gstin[14]}', expected '{result.expected_check_digit}' (likely a typo)"
        )

    result.valid = not result.errors
    return result
