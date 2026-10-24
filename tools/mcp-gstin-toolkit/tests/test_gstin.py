from gstin_toolkit.gstin import check_digit, validate_gstin
from gstin_toolkit.states import codes_match, state_code_for

# Widely published sample GSTIN used in GST documentation.
KNOWN_VALID = "27AAPFU0939F1ZV"


def test_known_valid_gstin():
    r = validate_gstin(KNOWN_VALID)
    assert r.valid, r.errors
    assert r.state == "Maharashtra"
    assert r.pan == "AAPFU0939F"
    assert r.pan_holder_type == "Firm / LLP"


def test_normalizes_case_and_separators():
    assert validate_gstin(" 27-aapfu 0939f1zv ").valid


def test_check_digit_typo_is_caught_with_expected_value():
    r = validate_gstin(KNOWN_VALID[:-1] + "X")
    assert not r.valid
    assert r.expected_check_digit == "V"
    assert any("check digit" in e for e in r.errors)


def test_check_digit_function():
    assert check_digit(KNOWN_VALID[:14]) == "V"


def test_bad_length_and_format():
    assert "length" in validate_gstin("27AAPFU0939F1Z").errors[0]
    assert "format" in validate_gstin("2XAAPFU0939F1ZV").errors[0]
    assert validate_gstin("").errors == ["empty value"]


def test_unknown_state_code():
    s = "00AAPFU0939F1Z"
    r = validate_gstin(s + check_digit(s))
    assert not r.valid
    assert any("unknown state code" in e for e in r.errors)


def test_state_lookup_handles_aliases():
    assert state_code_for("Karnataka") == "29"
    assert state_code_for("KA") == "29"
    assert state_code_for(" orissa ") == "21"
    assert state_code_for("Andhra Pradesh") == "37"
    assert state_code_for("Jammu & Kashmir") == "01"
    assert state_code_for("9") == "09"
    assert state_code_for("Atlantis") is None


def test_equivalent_state_codes():
    assert codes_match("28", "37")
    assert not codes_match("29", "33")
