import io
import json
import os
import sys

import pytest

from d3v_keyguard import cli
from d3v_keyguard.crypto import KdfParams
from d3v_keyguard.vault import Vault

from test_keyguard import FakeKeyring, FakePrompt

PIN = "correct-horse"
SECRET = "ghp_cli0123456789abcdefXYZ"
FAST = KdfParams(1, 1, 8)


@pytest.fixture
def cli_vault(tmp_path, monkeypatch):
    kr = FakeKeyring()
    path = tmp_path / "vault.json"
    v = Vault(path, keyring_backend=kr, kdf_params=FAST)
    v.create(PIN)
    v.put("gh", SECRET)
    v.lock()
    prompt = FakePrompt([PIN] * 5)
    monkeypatch.setattr(cli, "Vault", lambda *a, **k: Vault(path, keyring_backend=kr, kdf_params=FAST))
    monkeypatch.setattr(cli, "_prompt", lambda: prompt)
    monkeypatch.delenv("KEYGUARD_POLICY_FILE", raising=False)
    return types_ns(path=path, prompt=prompt, kr=kr)


def types_ns(**kw):
    import types

    return types.SimpleNamespace(**kw)


def test_exec_injects_env_redacts_output_and_shows_command(cli_vault, capfd):
    code = cli.main([
        "exec", "--env", "TOKEN=keyguard://gh", "--",
        sys.executable, "-c", "import os,sys; print('got', os.environ['TOKEN']); sys.exit(3)",
    ])
    out = capfd.readouterr().out
    assert code == 3
    assert SECRET not in out and "[REDACTED:keyguard://gh]" in out
    asked = cli_vault.prompt.asked[0]
    assert "TOKEN = keyguard://gh" in asked and "print('got'" in asked


def test_exec_survives_non_ascii_output_on_strict_cp1252_stdout(cli_vault, monkeypatch):
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252", errors="strict"))
    child = ("import os,sys; w=sys.stdout.buffer.write; w('arrow \\u2192 ok\\n'.encode()); w(b'bad \\xff byte\\n');"
             "[print('line', i) for i in range(20000)]; print(os.environ['TOKEN']); print('CHILD-END')")
    code = cli.main(["exec", "--env", "TOKEN=keyguard://gh", "--", sys.executable, "-c", child])
    sys.stdout.flush()
    data = raw.getvalue()
    assert code == 0
    assert b"CHILD-END" in data and "→".encode() in data and b"line 19999" in data
    assert SECRET.encode() not in data and b"[REDACTED:keyguard://gh]" in data


def test_exec_missing_command_is_127(cli_vault, capfd):
    assert cli.main(["exec", "--", "definitely-not-a-command-xyz"]) == 127
    assert "command not found" in capfd.readouterr().err


@pytest.mark.skipif(os.name != "nt", reason=".cmd shims are Windows-only")
def test_exec_runs_cmd_shims_on_windows(cli_vault, tmp_path, monkeypatch, capfd):
    (tmp_path / "hellocmd.cmd").write_text("@echo hello from cmd %TOKEN%\r\n")
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    assert cli.main(["exec", "--env", "TOKEN=keyguard://gh", "--", "hellocmd"]) == 0
    out = capfd.readouterr().out
    assert "hello from cmd [REDACTED:keyguard://gh]" in out and SECRET not in out


def test_exec_policy_denies_unlisted_command(cli_vault, tmp_path, monkeypatch, capfd):
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"exec:gh": ["gh"]}))
    monkeypatch.setenv("KEYGUARD_POLICY_FILE", str(policy))
    assert cli.main(["exec", "--env", "T=keyguard://gh", "--", sys.executable, "-c", "0"]) == 1
    assert "policy denies" in capfd.readouterr().err
    assert not cli_vault.prompt.asked  # refused before asking for the passphrase


def test_add_unlocks_and_stores_active_and_needs_force_to_replace(cli_vault, capfd):
    cli_vault.prompt.answers = ["new-value-123456", PIN]
    assert cli.main(["add", "demo_key"]) == 0
    assert "stored keyguard://demo_key (active)" in capfd.readouterr().out
    assert cli.main(["add", "demo_key"]) == 1
    cli_vault.prompt.answers = ["agent-value-123456"]
    assert cli.main(["add", "other", "--no-unlock"]) == 0
    assert "(pending)" in capfd.readouterr().out


def test_list_shows_handles_not_values(cli_vault, capfd):
    assert cli.main(["list"]) == 0
    out = capfd.readouterr().out
    assert "keyguard://gh\tactive" in out and SECRET not in out


def test_reject_discards_pending(cli_vault, capfd):
    Vault(cli_vault.path, keyring_backend=cli_vault.kr, kdf_params=FAST).put("planted", "planted-value-xyz")
    assert cli.main(["reject", "planted"]) == 0
    capfd.readouterr()
    assert cli.main(["list"]) == 0
    assert "planted" not in capfd.readouterr().out


def test_reveal_refused_when_piped(cli_vault, capfd):
    assert cli.main(["reveal", "gh"]) == 2
    captured = capfd.readouterr()
    assert SECRET not in captured.out + captured.err


def test_exec_rejects_bad_env_spec(cli_vault, capfd):
    assert cli.main(["exec", "--env", "TOKEN=gh", "--", sys.executable, "-c", "0"]) == 2
