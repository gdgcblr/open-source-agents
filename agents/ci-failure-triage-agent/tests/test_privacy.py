from collections import Counter

from triage.privacy import redact, scan

# Sensitive-looking values are assembled at runtime so nothing realistic is committed.
CARD = "4111" + " 1111" + " 1111" + " 1111"      # standard test PAN (passes Luhn)
BAD_CARD = "4111 1111 1111 1112"                    # fails Luhn: must be left alone
AADHAAR = "2345 6789 " + "0123"
PAN = "ABCDE" + "1234F"
SSN = "123-45-" + "6789"


def test_credit_card_luhn():
    assert CARD not in redact(f"paid with {CARD}")
    assert BAD_CARD in redact(f"order {BAD_CARD}")


def test_indian_ids():
    out = redact(f"aadhaar {AADHAAR} pan {PAN}")
    assert AADHAAR not in out and PAN not in out


def test_ssn_phone_mac_ipv6():
    out = redact(f"{SSN} +91 98765 43210 aa:bb:cc:dd:ee:ff 2001:db8::8a2e:370:7334 (415) 555-0132")
    for leaked in (SSN, "98765 43210", "aa:bb:cc:dd:ee:ff", "2001:db8", "555-0132"):
        assert leaked not in out


def test_home_directory_user():
    out = redact("File /home/alice/project/app.py and C:\\Users\\Bob\\src\\x.py")
    assert "alice" not in out and "Bob" not in out and "/project/app.py" in out


def test_ci_runner_users_not_personal():
    assert "/home/runner/work" in redact("/home/runner/work/repo")


def test_timestamps_versions_and_loopback_untouched():
    text = "[10:01:08] python 3.12.3 on 127.0.0.1 took 5.3s build 20241024"
    assert redact(text) == text


def test_internal_host():
    assert "registry.internal.example" not in redact("calling https://registry.internal.example/v2")


def test_pseudonyms_are_consistent_and_distinct():
    out = redact("a@x.io then a@x.io then b@x.io")
    toks = [w for w in out.split() if w.startswith("[EMAIL:")]
    assert toks[0] == toks[1] != toks[2]


def test_pseudonym_does_not_contain_value():
    assert "x.io" not in redact("a@x.io")


def test_idempotent():
    s = "bob@corp.io 10.0.3.17 DB_PASSWORD=hunter2hunter2 Bearer abcdefghijk123"
    once = redact(s)
    assert redact(once) == once


def test_custom_terms(monkeypatch):
    monkeypatch.setenv("TRIAGE_REDACT_TERMS", "Acme Corp, Priya")
    out = redact("customer Acme Corp reported by priya")
    assert "Acme" not in out and "priya" not in out.lower().replace("[custom_term", "")


def test_counts_are_kinds_and_numbers_only():
    stats = Counter()
    redact("a@b.io c@d.io 10.1.2.3", stats)
    assert stats["EMAIL"] == 2 and stats["IPV4"] == 1
    assert scan(["a@b.io"]) == {"EMAIL": 1}
