"""Egress guardrail tests (offline)."""

import pytest

from aran import guard, redact_text
from aran.detectors import verhoeff_check_digit

AADHAAR = "4821 5730 962" + verhoeff_check_digit("48215730962")
PAN = "ABCPK1234F"


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ARAN_HOME", str(tmp_path))


def test_redacted_text_passes():
    r = redact_text(f"Applicant Name: Karthik Ramanathan PAN {PAN}", "kyc", use_llm=False)
    assert guard.find_leaks(r.redacted, r.session_id) == []


def test_vault_tripwire_catches_known_value_even_reformatted():
    r = redact_text(f"Aadhaar {AADHAAR}", "kyc", use_llm=False)
    leaks = guard.find_leaks(f"oops: {AADHAAR.replace(' ', '')}", r.session_id)
    assert {(l.type, l.check) for l in leaks} >= {("AADHAAR", "vault")}
    assert all(AADHAAR not in str(l) for l in leaks)  # never echoes the value


def test_detector_catches_pii_that_never_went_through_aran():
    leaks = guard.find_leaks(f"new info, PAN {PAN}", session_id=None)
    assert [l.type for l in leaks] == ["PAN"]


def test_kept_types_do_not_trip():
    assert guard.find_leaks("IFSC HDFC0001234, amount 86,500", session_id=None) == []
