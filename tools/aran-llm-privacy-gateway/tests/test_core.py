"""Offline tests: no Ollama or network needed (use_llm=False)."""

import json

import pytest

from aran import audit, detectors, redact_text, restore
from aran.detectors import gstin_check_char, verhoeff_check_digit

# Synthetic identifiers built with valid checksums. They do not belong to anyone.
AADHAAR = "4821 5730 962" + verhoeff_check_digit("48215730962")
GSTIN = "29ABCPK1234F1Z" + gstin_check_char("29ABCPK1234F1Z")
PAN = "ABCPK1234F"


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ARAN_HOME", str(tmp_path))


def types(text):
    return {f.type for f in detectors.detect(text)}


def test_aadhaar_requires_valid_verhoeff():
    assert "AADHAAR" in types(f"Aadhaar: {AADHAAR}")
    bad = AADHAAR[:-1] + str((int(AADHAAR[-1]) + 1) % 10)
    assert "AADHAAR" not in types(f"Aadhaar: {bad}")


def test_gstin_wins_over_embedded_pan():
    found = detectors.detect(f"GSTIN {GSTIN}")
    assert [f.type for f in found] == ["GSTIN"]
    assert found[0].validated


def test_indian_identifiers():
    text = (
        f"PAN {PAN}, phone +91 98450 12345, mail ravi.k@example.com, UPI ravik@okaxis, "
        "IFSC HDFC0001234, A/c No: 50100234567812, DOB: 14/03/1991, PIN 560034, "
        "card 4111 1111 1111 1111, UHID: BLR-88231"
    )
    assert types(text) == {
        "PAN", "PHONE", "EMAIL", "UPI", "IFSC", "ACCOUNT_NUMBER", "DOB", "PINCODE", "CARD",
        "MEDICAL_ID",
    }


def test_redact_and_restore_round_trip():
    text = f"Applicant PAN {PAN}. Statement shows PAN {PAN} and Aadhaar {AADHAAR}."
    r = redact_text(text, "kyc", use_llm=False)
    assert PAN not in r.redacted and AADHAAR not in r.redacted
    assert r.redacted.count("<PAN_1>") == 2  # same value -> same token
    assert restore(r.redacted, r.session_id) == text


def test_session_tokens_are_consistent_across_documents():
    a = redact_text(f"PAN card: {PAN}", "kyc", use_llm=False)
    b = redact_text(f"Bank KYC PAN {PAN}", "kyc", session_id=a.session_id, use_llm=False)
    assert "<PAN_1>" in a.redacted and "<PAN_1>" in b.redacted


def test_profile_keeps_and_generalises():
    r = redact_text("IFSC HDFC0001234 DOB: 01/01/1990", "kyc", use_llm=False)
    assert "HDFC0001234" in r.redacted  # kyc keeps IFSC
    assert "[age " in r.redacted and "1990" not in r.redacted


def test_restore_accepts_model_token_variants():
    r = redact_text(f"PAN {PAN}", "kyc", use_llm=False)
    assert restore("Holder of [PAN_1] / PAN_1", r.session_id) == f"Holder of {PAN} / {PAN}"


def test_audit_log_never_contains_raw_values(tmp_path):
    redact_text(f"PAN {PAN} Aadhaar {AADHAAR} mail ravi.k@example.com", "kyc", use_llm=False)
    log = (tmp_path / "audit.jsonl").read_text()
    for raw in (PAN, AADHAAR, "ravi.k@example.com"):
        assert raw not in log
    entry = json.loads(log.splitlines()[0])
    assert entry["found"]["PAN"] == 1 and entry["raw_values_sent"] == 0
    assert audit.summarise(audit.read())["pii_found"] == 3


def test_vault_file_is_private(tmp_path):
    r = redact_text(f"PAN {PAN}", "kyc", use_llm=False)
    mode = (tmp_path / "vault" / f"{r.session_id}.json").stat().st_mode & 0o777
    assert mode == 0o600


def test_unknown_profile_rejected():
    with pytest.raises(ValueError):
        redact_text("x", "nope", use_llm=False)


def test_labelled_names_and_multiline_address_without_llm():
    text = (
        "Patient Name: Meenakshi Sundaram\n"
        "Address: No. 12, 4th Cross,\nIndiranagar 2nd Stage, Bengaluru\n"
        "PIN: 560038\nReferred By: Dr. Priya Venkatesh"
    )
    r = redact_text(text, "health", use_llm=False)
    for leaked in ("Meenakshi", "Indiranagar", "4th Cross", "560038", "Priya"):
        assert leaked not in r.redacted


def test_ocr_mode_fails_closed_on_misread_ids():
    # OCR dropped a letter from the PAN and misread one Aadhaar digit.
    bad_aadhaar = AADHAAR[:-1] + str((int(AADHAAR[-1]) + 1) % 10)
    text = f"Permanent Account Number\nBQPR4821M\nAadhaar {bad_aadhaar}"
    plain = redact_text(text, "kyc", use_llm=False)
    scanned = redact_text(text, "kyc", use_llm=False, kind="image")
    assert "BQPR4821M" in plain.redacted  # text mode: not a valid PAN, left alone
    assert "BQPR4821M" not in scanned.redacted and bad_aadhaar not in scanned.redacted
