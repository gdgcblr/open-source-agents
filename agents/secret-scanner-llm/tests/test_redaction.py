from secret_scanner.redaction import redact_line, redact_value
from secret_scanner.scanner import scan_text

from . import helpers as H


def test_redact_value_format():
    r = redact_value(H.stripe(), keep=11)
    assert r.startswith("sk_live_51H****(") and "chars" in r
    assert H.stripe() not in r and H.stripe()[11:] not in r


def test_prefix_is_capped_for_short_values():
    assert redact_value("abcdefghijkl", keep=20) == "abcd****(12 chars, alnum)"
    assert redact_value("abcdefghi", keep=20) == "****(9 chars, alnum)"
    assert redact_value("abc", keep=5).startswith("****(")


def test_redact_line_hides_secret_and_neighbours():
    line = f'url = "{H.db_url()}"; k = "{H.aws()}"'
    out = redact_line(line)
    assert "Vq83nKd02Lx" not in out and H.aws() not in out
    assert "svc_app" in out  # non-secret parts remain readable


def test_pem_body_lines_are_redacted_but_header_kept():
    text = "\n".join([H.pem_header(), H.PEM_BODY, "-----END RSA PRIVATE KEY-----"])
    c = scan_text("k.txt", text)[0]
    blob = "\n".join(c.context)
    assert H.PEM_BODY not in blob and H.PEM_BODY[:30] not in blob
    assert "PRIVATE KEY" in c.redacted_value


def test_candidate_never_contains_raw():
    secrets = [H.aws(), H.github(), H.stripe(), H.google(), H.slack(), H.password(), "Vq83nKd02Lx"]
    src = "\n".join(f'api_key{i} = "{s}"' for i, s in enumerate(secrets[:-1])) + f'\nDB = "{H.db_url()}"'
    for c in scan_text("a.py", src):
        blob = repr(c.to_dict())
        for s in secrets:
            assert s not in blob
            assert s[len(s) // 2:] not in blob
