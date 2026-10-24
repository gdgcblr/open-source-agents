import pytest

from prompt_enhancer import registry


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    """Isolate every test from the developer's environment and cache."""
    for var in (
        "PROMPT_ENHANCER_MODEL", "ANTHROPIC_MODEL", "PROMPT_ENHANCER_PROFILES_DIR", "PROMPT_ENHANCER_MIN_WORDS",
        "PROMPT_ENHANCER_LONG_CONTEXT_TOKENS", "PROMPT_ENHANCER_DISABLE", "PROMPT_ENHANCER_SHOW_SUGGESTIONS",
        "PROMPT_ENHANCER_DISABLE_RULES", "PROMPT_ENHANCER_RESTATE", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("PROMPT_ENHANCER_CACHE_DIR", str(tmp_path / "cache"))
    registry.clear_cache()
    yield
    registry.clear_cache()
