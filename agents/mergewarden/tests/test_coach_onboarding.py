"""Simulator onboarding: instant welcome with the onboarding questions, English-only
language lock, and GitHub/LinkedIn links in the profile. Offline, fake model."""

from __future__ import annotations

import asyncio

import pytest
from google.adk.sessions import InMemorySessionService

from mergewarden import source
from mergewarden.coach import config, guardrails, tools
from mergewarden.coach.agent import build
from mergewarden.coach.service import WELCOME, Coach
from test_coach import FakeLlm, data_dir  # noqa: F401  (fixture)


class SpyLlm(FakeLlm):
    """Records which agent answered and what its instructions said."""

    seen: list = []

    def _decide(self, agent, fr, text, user_text, si):
        SpyLlm.seen.append((agent, si))
        return self._say("Nice to meet you! Which of those projects excites you most?")


@pytest.fixture
def coach(data_dir, monkeypatch):  # noqa: F811
    monkeypatch.setattr(source, "github_api", lambda path: [])
    SpyLlm.seen = []
    return Coach(agent=build(model=SpyLlm()), store=data_dir, session_service=InMemorySessionService(),
                 limiter=guardrails.RateLimiter(limit=100, window_s=600))


def test_welcome_asks_onboarding_questions_once(coach):
    async def run():
        uid = "sim:new-student"
        w = await coach.welcome(uid, force_language="English")
        assert w.text == WELCOME and w.language == "English"
        for ask in ("GitHub profile link", "LinkedIn profile link", "Languages and tools", "hours a week"):
            assert ask in w.text
        assert SpyLlm.seen == []  # no model call: instant
        again = await coach.welcome(uid, force_language="English")  # page reload before answering
        assert again.text == WELCOME
        uh = guardrails.hash_user(uid)
        s = await coach.sessions.get_session(app_name="newcomer_coach", user_id=uh, session_id=coach._sid(uh))
        assert [e.author for e in s.events].count("onboarding_agent") == 1  # recorded once

        # The student's answer goes straight to the onboarding agent, which knows the questions were asked.
        await coach.handle_message(uid, text="I'm Asha, 3rd-year CSE. github.com/asha-dev, Python, 4 hrs/week",
                                   force_language="English")
        agent, si = SpyLlm.seen[0]
        assert agent == "onboarding_agent" and '"welcome_sent": true' in si
        assert await coach.welcome(uid) is None  # returning student: no second onboarding

    asyncio.run(run())


def test_language_lock_forces_english(coach):
    async def run():
        r = await coach.handle_message("sim:ml-student", text="നമസ്കാരം, എനിക്ക് Python അറിയാം",
                                       force_language="English")
        assert r.language == "English"
        assert any("LANGUAGE LOCK: reply ONLY in English" in si for _, si in SpyLlm.seen)
        SpyLlm.seen.clear()
        free = await coach.handle_message("whatsapp:+919800000009", text="നമസ്കാരം")  # WhatsApp: not locked
        assert free.language == "Malayalam"
        assert not any("LANGUAGE LOCK" in si for _, si in SpyLlm.seen)

    asyncio.run(run())


def test_github_and_linkedin_links():
    assert tools._gh_link("https://github.com/asha-dev") == "asha-dev"
    assert tools._gh_link("github.com/asha-dev/") == "asha-dev"
    assert tools._gh_link("@asha-dev") == "asha-dev"
    assert tools._gh_link("https://github.com/asha-dev?tab=repositories") == "asha-dev"
    assert tools._gh_link("https://evil.example/github.com/x") == ""
    assert tools._li_link("linkedin.com/in/asha-k-123/") == "https://www.linkedin.com/in/asha-k-123"
    assert tools._li_link("https://in.linkedin.com/in/asha") == "https://www.linkedin.com/in/asha"
    assert tools._li_link("https://linkedin.com.evil.io/in/asha") == ""


def test_save_profile_stores_links(data_dir):  # noqa: F811
    class Ctx:
        state = {"user_hash": "u9"}

    import mergewarden.coach.github_match as gm

    def fake_analyze(handle):
        return {"handle": handle, "bio": "", "top_languages": ["Python"], "topics": ["fastapi"],
                "recent_projects": [], "merged_external_prs": 0, "external_prs": 0, "level": "beginner", "signals": []}

    orig, gm.analyze_profile = gm.analyze_profile, fake_analyze
    try:
        out = asyncio.run(tools.save_profile("English", "python", "4 hours", github_handle="https://github.com/asha-dev",
                                             linkedin_url="linkedin.com/in/asha-k", name="Asha", tool_context=Ctx()))
    finally:
        gm.analyze_profile = orig
    assert out["github_profile"]["top_languages"] == ["Python"]  # GitHub read automatically from the link
    p = data_dir.get_user("u9")["profile"]
    assert p["github"] == "asha-dev" and p["linkedin"] == "https://www.linkedin.com/in/asha-k" and p["name"] == "Asha"
    assert p["github_summary"]["level"] == "beginner"


def test_welcome_endpoint(coach, monkeypatch):
    from fastapi.testclient import TestClient

    from mergewarden.coach import server

    monkeypatch.setattr(config, "SIMULATOR_FORCE_LANGUAGE", "English")
    client = TestClient(server.make_app(coach=coach))
    msg = client.post("/api/welcome", data={"user_id": "fresh1"}).json()["message"]
    assert msg["text"] == WELCOME and msg["language"] == "English"
