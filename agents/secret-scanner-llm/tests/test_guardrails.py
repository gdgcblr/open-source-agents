import logging

import pytest

from secret_scanner.guardrails import (PathNotAllowed, confine, contains_raw_secret, mask_obj,
                                       mask_text, safe_logger)
from secret_scanner.triage import decide
from secret_scanner.models import Candidate, TriageResult

from . import helpers as H


def test_confine_inside_and_relative(tmp_path):
    (tmp_path / "a").mkdir()
    assert confine("a", tmp_path) == (tmp_path / "a").resolve()
    assert confine(tmp_path / "a", tmp_path) == (tmp_path / "a").resolve()


def test_confine_rejects_outside_dotdot_and_symlink(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside)
    for bad in ("..", str(outside), "link", "../outside", "/etc"):
        with pytest.raises(PathNotAllowed):
            confine(bad, root)


def test_scan_root_confinement(tmp_path):
    from secret_scanner.scanner import scan
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(PathNotAllowed):
        scan(tmp_path, use_llm=False, root=root)


def test_symlink_files_are_not_followed(tmp_path):
    from secret_scanner.scanner import scan
    secret_dir = tmp_path / "elsewhere"
    secret_dir.mkdir()
    (secret_dir / "s.py").write_text(f'k = "{H.aws()}"\n')
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "l.py").symlink_to(secret_dir / "s.py")
    assert scan(proj, use_llm=False).findings == []


def test_mask_text_and_obj_and_idempotent():
    raw = f'token = "{H.github()}"'
    assert H.github() not in mask_text(raw)
    once = mask_text(raw)
    assert mask_text(once) == once  # already-redacted values are left alone
    assert H.github() not in str(mask_obj({"a": [raw, {"b": raw}]}))


def test_llm_text_is_masked_in_findings():
    c = Candidate("f.py", 1, "r", "k", "x", [], False, False, "medium")
    f = decide(c, TriageResult("real", 0.9, f"it is {H.github()}", f"rotate {H.aws()}", "m", 0))
    assert H.github() not in f.reason and H.aws() not in f.remediation


def test_log_masking(caplog):
    lg = safe_logger("secret_scanner.test_sink")
    with caplog.at_level(logging.DEBUG):
        lg.warning("leaked %s", H.github())
    assert H.github() not in caplog.text and "ghp_" in caplog.text


def test_contains_raw_secret():
    assert contains_raw_secret(f"my key is {H.aws()}")
    assert contains_raw_secret(f'password = "{H.password()}"')
    assert not contains_raw_secret('token = "ghp_a1B****(40 chars, base64-like)"')
    assert not contains_raw_secret("Please scan ./src for secrets")


def test_scanner_tools_are_read_only():
    """No write/delete/exec/network primitives in the scanner's own code (network = Ollama only)."""
    import pathlib
    import re
    src = "".join(p.read_text() for p in pathlib.Path(__file__).parent.parent.joinpath("secret_scanner").glob("*.py"))
    for forbidden in (r"\.write_text\(", r"\.write_bytes\(", r"os\.remove", r"os\.unlink", r"shutil\.",
                      r"os\.system", r"\beval\(", r"\bexec\(", r"requests\.", r"urllib"):
        assert not re.search(forbidden, src), forbidden
    # subprocess is only used for read-only git commands
    assert set(re.findall(r'\["git"[^\]]*\]', src))
    assert not re.search(r"git[^\n]*(push|commit|rm|reset|checkout|clean)", src)
