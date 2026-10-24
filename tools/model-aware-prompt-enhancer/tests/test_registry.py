import json
from urllib.parse import urlparse

import pytest

from prompt_enhancer import registry
from prompt_enhancer.registry import ProfileError


@pytest.mark.parametrize(
    "model,profile,how",
    [
        ("claude-opus-5-5", "anthropic-claude", "pattern"),
        ("claude-sonnet-5", "anthropic-claude", "pattern"),
        ("us.anthropic.claude-haiku-4-5-20251001-v1:0", "anthropic-claude", "pattern"),
        ("gpt-4.1", "openai-gpt", "pattern"),
        ("gpt-6-astra", "openai-gpt", "pattern"),
        ("o3", "openai-reasoning", "pattern"),
        ("o4-mini", "openai-reasoning", "pattern"),
        ("gemini-3-pro", "google-gemini", "pattern"),
        ("models/gemini-2.5-flash", "google-gemini", "pattern"),
        ("GEMINI-3-PRO", "google-gemini", "pattern"),
        ("anthropic-claude", "anthropic-claude", "exact-id"),
        ("gemini", "google-gemini", "alias"),
        ("gpt", "openai-gpt", "alias"),
        ("claude", "anthropic-claude", "alias"),
    ],
)
def test_resolves_known_models(model, profile, how):
    res = registry.resolve(model)
    assert (res.profile.id, res.how, res.matched) == (profile, how, True)


@pytest.mark.parametrize("model", ["llama-4-scout", "mistral-large", "omni-model", "", "   ", None])
def test_unknown_or_missing_model_falls_back_to_generic(model):
    res = registry.resolve(model)
    assert res.profile.id == "generic" and not res.matched and res.how == "fallback"


def test_variants_are_model_specific():
    opus46 = registry.resolve("claude-opus-4-6").profile
    sonnet = registry.resolve("claude-sonnet-5").profile
    opus5 = registry.resolve("claude-opus-5").profile
    opus55 = registry.resolve("claude-opus-5-5").profile
    assert opus46.variant == "claude-opus-4.5-4.6" and "claude.soften-emphasis" in {g.id for g in opus46.guidelines}
    assert sonnet.variant is None and "claude.soften-emphasis" not in {g.id for g in sonnet.guidelines}
    assert opus5.variant == "claude-opus-5"
    assert opus55.variant is None  # Opus 5.5 is a different model from Opus 5
    g36 = registry.resolve("gemini-3.6-pro").profile
    g30 = registry.resolve("gemini-3-pro").profile
    assert "sampling_parameters" in {c.name for c in g36.capabilities}
    assert "sampling_parameters" not in {c.name for c in g30.capabilities}


def test_harness_default_profile_used_when_model_missing():
    h = registry.get_harness("claude-code")
    res = registry.resolve(None, h)
    assert res.profile.id == "anthropic-claude" and res.how == "harness-default"


def test_detect_model_prefers_explicit_then_env(monkeypatch):
    h = registry.get_harness("claude-code")
    assert registry.detect_model(h) is None
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
    assert registry.detect_model(h) == "claude-haiku-4-5"
    monkeypatch.setenv("PROMPT_ENHANCER_MODEL", "claude-opus-5-5")
    assert registry.detect_model(h) == "claude-opus-5-5"
    assert registry.detect_model(h, "gpt-4.1") == "gpt-4.1"


def test_every_claim_is_sourced_versioned_and_evidence_tagged():
    for p in registry.load_models().values():
        assert p.profile_version.count(".") == 2 and p.last_verified
        for s in p.sources:
            u = urlparse(s.url)
            assert u.scheme == "https" and u.hostname in registry.OFFICIAL_DOC_HOSTS
        items = list(p.guidelines) + [g for v in p.variants for g in v.guidelines]
        for g in items:
            assert g.source in p.sources and g.section and g.evidence in registry.EVIDENCE
        for c in list(p.capabilities) + [c for v in p.variants for c in v.capabilities]:
            assert c.evidence in registry.EVIDENCE and c.source in p.sources


def test_profiles_do_not_claim_context_windows():
    # Context limits are only allowed when verified per model; none are verified yet.
    for p in registry.load_models().values():
        assert not any("context_window" in c.name for c in p.capabilities)


def test_profiles_are_cached():
    a = registry.load_models()
    assert registry.load_models() is a
    registry.clear_cache()
    assert registry.load_models() is not a


def _write_profile(tmp_path, raw=None, **overrides):
    base = json.loads((registry.BUILTIN_DIR / "models" / "generic.json").read_text())
    base.update(id="custom-test", match=["^custom-"], aliases=[])
    base.update(overrides)
    d = tmp_path / "profiles" / "models"
    d.mkdir(parents=True)
    (d / "custom.json").write_text(raw if raw is not None else json.dumps(base))
    return tmp_path / "profiles"


def test_extra_profile_dir_is_loaded(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPT_ENHANCER_PROFILES_DIR", str(_write_profile(tmp_path)))
    assert registry.resolve("custom-model-1").profile.id == "custom-test"


@pytest.mark.parametrize(
    "overrides,msg",
    [
        ({"sources": [{"id": "x", "title": "x", "url": "http://ai.google.dev/x"}]}, "https"),
        ({"sources": [{"id": "x", "title": "x", "url": "https://random-blog.example.com/tips"}]}, "official"),
        ({"profile_version": "1.0"}, "semver"),
        ({"last_verified": "yesterday"}, "last_verified"),
        ({"match": ["(unclosed"]}, "bad match pattern"),
        ({"schema_version": 1}, "schema_version"),
        ({"guidelines": [{"id": "g", "kind": "advice", "text": "t", "source": "nope", "section": "s", "evidence": "documented"}]}, "unknown source"),
        ({"guidelines": [{"id": "g", "kind": "advice", "text": "t", "source": "claude", "section": "s", "evidence": "vibes"}]}, "evidence"),
        ({"guidelines": [{"id": "g", "kind": "magic", "text": "t", "source": "claude", "section": "s", "evidence": "documented"}]}, "kind"),
        ({"guidelines": [{"id": "g", "kind": "advice", "text": "t", "source": "claude", "section": "s", "evidence": "documented", "when": {"weather": 1}}]}, "unknown 'when'"),
    ],
)
def test_invalid_profiles_are_rejected(tmp_path, monkeypatch, overrides, msg):
    monkeypatch.setenv("PROMPT_ENHANCER_PROFILES_DIR", str(_write_profile(tmp_path, **overrides)))
    with pytest.raises(ProfileError, match=msg):
        registry.load_models()


@pytest.mark.parametrize("raw", ["{not json", "[]", ""])
def test_malformed_profile_files_raise_profile_error(tmp_path, monkeypatch, raw):
    monkeypatch.setenv("PROMPT_ENHANCER_PROFILES_DIR", str(_write_profile(tmp_path, raw=raw)))
    with pytest.raises(ProfileError):
        registry.load_models()


def test_unknown_harness_raises():
    with pytest.raises(KeyError):
        registry.get_harness("nope")
