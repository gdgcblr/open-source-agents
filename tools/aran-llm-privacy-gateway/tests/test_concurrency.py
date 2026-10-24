"""Parallel redactions in one session (agents call tools in parallel) must not lose tokens."""

from concurrent.futures import ThreadPoolExecutor

from aran import redact_text, restore
from aran.vault import Vault, new_session_id


def test_parallel_redactions_share_one_consistent_vault(tmp_path, monkeypatch):
    monkeypatch.setenv("ARAN_HOME", str(tmp_path))
    session = new_session_id()
    docs = [f"Applicant Name: Ravi {chr(65 + i)}rumugam\nMobile: 9{i:09d}" for i in range(24)]

    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(lambda d: redact_text(d, "kyc", session, use_llm=False), docs))

    vault = Vault(session)
    assert len(vault.tokens) == 48  # 24 names + 24 phones, none lost to a racing save
    assert len({e["value"] for e in vault.tokens.values()}) == 48  # no token reused for two values
    for doc, r in zip(docs, results):
        assert restore(r.redacted, session) == doc
