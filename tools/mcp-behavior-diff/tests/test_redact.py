from mcp_behavior_diff.redact import REDACTED, clean_json, clean_text, redact_text, sanitize_text, truncate_text

FAKE_GH = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
FAKE_AWS = "AKIA" + "ABCDEFGHIJKLMNOP"


def test_ansi_and_control_chars_stripped():
    assert sanitize_text("\x1b[31mred\x1b[0m\x07\x00ok") == "redok"


def test_osc_title_injection_stripped():
    assert sanitize_text("a\x1b]0;pwned\x07b") == "ab"


def test_bidi_and_zero_width_made_visible():
    out = sanitize_text("a‮b​c")
    assert "‮" not in out and "​" not in out
    assert "\\u202e" in out and "\\u200b" in out


def test_known_token_shapes_redacted():
    text = f"gh={FAKE_GH} aws={FAKE_AWS} Bearer abcdefghijklmnopqrstuvwxyz012345"
    out = redact_text(text)
    assert FAKE_GH not in out and FAKE_AWS not in out and "abcdefghijklmnop" not in out


def test_key_value_keeps_key_drops_value():
    assert redact_text("password=hunter2hunter2") == f"password={REDACTED}"


def test_literal_secret_values_redacted():
    assert redact_text("db at postgres://u:s3cr3tpw@h", ["s3cr3tpw"]) == f"db at postgres://u:{REDACTED}@h"


def test_short_literals_ignored_to_avoid_mangling():
    assert redact_text("a b c", ["a"]) == "a b c"


def test_escape_cannot_hide_a_secret_from_redaction():
    split = "ghp_\x1b[0mA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
    assert "A1b2C3d4" not in clean_text(split, max_bytes=1000)


def test_truncate_marks_and_caps():
    out = truncate_text("x" * 100, 10)
    assert out.startswith("x" * 10) and "TRUNCATED" in out


def test_clean_json_recurses_keys_and_values():
    out = clean_json({"k\x1b[1m": ["v\x07", {"t": f"token={FAKE_GH}"}], "n": 3}, max_bytes=1000)
    assert out == {"k": ["v", {"t": f"token={REDACTED}"}], "n": 3}


def test_secret_key_value_redacted_even_without_known_shape():
    out = clean_json({"password": "abc", "note": "ok", "nested": {"api_key": "zzz"}}, max_bytes=1000)
    assert out["password"].startswith("[REDACTED:") and "abc" not in str(out)
    assert out["nested"]["api_key"].startswith("[REDACTED:") and out["note"] == "ok"


def test_fingerprint_is_stable_within_a_run_so_changes_stay_visible():
    a = clean_json({"token": "one"}, max_bytes=100)
    b = clean_json({"token": "one"}, max_bytes=100)
    c = clean_json({"token": "two"}, max_bytes=100)
    assert a == b and a != c


def test_secret_key_inside_json_text_is_redacted():
    out = redact_text('{"password": "correct-horse", "n": 1, "api_key": 12345, "ok": "keep"}')
    assert "correct-horse" not in out and "12345" not in out and '"ok": "keep"' in out
