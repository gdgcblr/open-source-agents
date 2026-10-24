"""Profile agent: turns a free-text sign-up into an anonymous, structured profile."""

from __future__ import annotations

import re

from pydantic import BaseModel

from .llm import LLM
from .models import INTERESTS, Goal, Profile, Role

MAX_INTERESTS = 5

PROMPT = """You build anonymous networking profiles for attendees of a developer event.

From the attendee's sign-up text, return:
- role: the single best fit.
- interests: up to {max_interests} topics, chosen ONLY from this list: {interests}
- goals: what they want from meeting people, chosen from the allowed values.
- one_liner: at most 15 words introducing them to strangers. It must NOT contain
  their name, employer, college, handle, email, phone or any other identifying detail.

Sign-up text:
\"\"\"{about}\"\"\"
"""


class _Draft(BaseModel):
    role: Role
    interests: list[str]
    goals: list[Goal]
    one_liner: str


# Offline fallback: keyword rules. Crude, but deterministic and good enough to run the
# event (and the simulator) without a key.
_INTEREST_RULES = {
    "agents": r"\bagent(s|ic)?\b|\badk\b|langgraph|crewai|multi-agent",
    "llms": r"\bllms?\b|\bgpt\b|gemini|claude|\bgenai\b|language model|prompt",
    "rag": r"\brag\b|retrieval|vector (db|database|search)|embeddings?",
    "mlops": r"mlops|model serving|deploy(ing)? models|inference",
    "computer-vision": r"computer vision|\bcv\b|image|video|object detection",
    "data": r"\bdata\b|analytics|\bsql\b|spark|pipelines?|warehouse",
    "web": r"\bweb\b|frontend|front-end|react|next\.?js|full[- ]?stack",
    "mobile": r"mobile|android|\bios\b|flutter|kotlin|swift",
    "cloud": r"\bcloud\b|\bgcp\b|\baws\b|azure|serverless|cloud run",
    "devops": r"devops|kubernetes|\bk8s\b|docker|ci/cd|terraform|\bsre\b",
    "security": r"security|pentest|appsec|infosec",
    "design": r"\bdesign(er|ing)?\b|\bux\b|\bui\b|figma",
    "startups": r"startup|founder|founding|bootstrapp",
    "open-source": r"open[- ]source|\boss\b|maintainer",
    "research": r"research|\bphd\b|paper|thesis",
    "gamedev": r"\bgames?\b|gamedev|unity|unreal",
    "fintech": r"fintech|payments?|banking|\bbank\b|\bupi\b",
    "healthtech": r"health|medical|clinic",
    "edtech": r"edtech|education|teaching|learning platform",
}
_ROLE_RULES = [  # first match wins
    (Role.founder, r"founder|\bceo\b|\bcto\b|my startup"),
    (Role.researcher, r"researcher|\bphd\b|research (scientist|engineer)"),
    (Role.designer, r"\bdesigner\b|ux designer|product designer"),
    (Role.product, r"product manager|\bpm\b|product owner"),
    (Role.student, r"student|college|university|undergrad|final year|\bb\.?tech\b"),
    (Role.developer, r"developer|engineer|\bsde\b|programmer|\bdev\b|backend|frontend"),
]
_GOAL_RULES = {
    Goal.hire: r"hiring|we're hiring|recruit|looking for (engineers|developers|interns)",
    Goal.get_hired: r"job|internship|looking for (a )?(role|position|opportunit)|open to work",
    Goal.cofounder: r"co-?founder",
    Goal.learn: r"\bto learn\b|\blearn more\b|beginner|new to|getting started",  # not "machine learning"
    Goal.mentor: r"mentor|guide|happy to help",
    Goal.collaborate: r"collaborat|build together|contributors|team ?mates?|partner",
}


def _matches(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE) is not None


def extract_offline(about: str) -> Profile:
    interests = [tag for tag, pat in _INTEREST_RULES.items() if _matches(pat, about)][:MAX_INTERESTS]
    role = next((r for r, pat in _ROLE_RULES if _matches(pat, about)), Role.other)
    goals = [g for g, pat in _GOAL_RULES.items() if _matches(pat, about)] or [Goal.network]
    topics = ", ".join(interests[:3]) or "a bit of everything"
    return Profile(role=role, interests=interests, goals=goals, one_liner=f"{role.value.capitalize()} into {topics}.")


def _clean(draft: _Draft) -> Profile:
    """Never trust the model's output shape: keep only known interests, cap list sizes."""
    interests = list(dict.fromkeys(i.strip().lower() for i in draft.interests if i.strip().lower() in INTERESTS))
    goals = list(dict.fromkeys(draft.goals)) or [Goal.network]
    return Profile(
        role=draft.role,
        interests=interests[:MAX_INTERESTS],
        goals=goals,
        one_liner=" ".join(draft.one_liner.split()[:15]),
    )


class ProfileAgent:
    def __init__(self, llm: LLM):
        self.llm = llm

    def build(self, about: str) -> Profile:
        prompt = PROMPT.format(max_interests=MAX_INTERESTS, interests=", ".join(INTERESTS), about=about[:2000])
        draft = self.llm.structured(prompt, _Draft)
        return _clean(draft) if draft else extract_offline(about)
