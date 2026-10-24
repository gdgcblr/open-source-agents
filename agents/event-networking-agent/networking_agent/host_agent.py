"""Room host agent: tells a new room why they were put together and gives them an icebreaker."""

from __future__ import annotations

import random
from collections import Counter

from pydantic import BaseModel

from .llm import LLM
from .matchmaker import goals_complement
from .models import Attendee, Goal

PROMPT = """You host a small room of strangers at a developer event. They were grouped by
an algorithm and are about to chat, then maybe meet in person.

Members (anonymous nicknames):
{members}

Topics two or more of them share: {shared}

Write:
- why: one or two friendly sentences on why this group makes sense. Name the nicknames.
- icebreaker: one specific, open question that everyone in the room can answer.
Keep it short, warm and concrete. No emojis, no corporate tone.
"""

_GOAL_PHRASES = {
    frozenset({Goal.hire, Goal.get_hired}): "{a} is hiring and {b} is looking",
    frozenset({Goal.learn, Goal.mentor}): "{b} is happy to mentor and {a} wants to learn",
    frozenset({Goal.cofounder}): "{a} and {b} are both looking for a cofounder",
    frozenset({Goal.collaborate}): "{a} and {b} both want people to build with",
}
_ICEBREAKERS = {
    "agents": "What is one task you would hand to an agent tomorrow if you trusted it fully?",
    "llms": "What is the most surprising thing an LLM has got right, or badly wrong, for you?",
    "rag": "What is the messiest data you have tried to make searchable?",
    "startups": "What problem would you quit your job to work on?",
    "open-source": "Which open-source project would you most like to contribute to?",
    "design": "What app have you used recently that felt delightful, and why?",
    "research": "What is a result you read recently that changed your mind?",
    "cloud": "What is the worst cloud bill or outage story you have lived through?",
    "mlops": "What broke the first time you put a model in front of real users?",
    "devops": "What is one thing you automated that saved you the most pain?",
    "security": "What is the scariest security hole you have seen in the wild?",
    "data": "What is the most useful dashboard or dataset you have ever built?",
    "web": "Which framework did you most recently switch to, and was it worth it?",
    "mobile": "What is the app on your phone you would rebuild if you could?",
    "fintech": "What is one money problem in India you wish software would fix?",
}
_GENERIC = [
    "What are you building right now, and what is the hardest part?",
    "What brought you to this event, honestly?",
    "What is one tool you could not work without this year?",
]


class RoomIntro(BaseModel):
    why: str
    icebreaker: str


def shared_interests(members: list[Attendee]) -> list[str]:
    counts = Counter(i for m in members for i in m.profile.interests)
    return [tag for tag, c in counts.most_common() if c >= 2]


def _goal_line(members: list[Attendee]) -> str | None:
    for x in members:
        for y in members:
            if x.id >= y.id or not goals_complement(x.profile, y.profile):
                continue
            for gx in x.profile.goals:
                for gy in y.profile.goals:
                    key = frozenset({gx, gy})
                    if key in _GOAL_PHRASES:
                        # Order the pair so {a} is the hirer / learner in the phrase.
                        a, b = (x, y) if gx in (Goal.hire, Goal.learn) or gx == gy else (y, x)
                        return _GOAL_PHRASES[key].format(a=a.nickname, b=b.nickname)
    return None


def intro_offline(members: list[Attendee], seed: int = 0) -> RoomIntro:
    shared = shared_interests(members)
    parts = []
    if shared:
        parts.append(f"You all orbit {', '.join(shared[:2])}")
    goal = _goal_line(members)
    if goal:
        parts.append(goal)
    why = ("; ".join(parts) + ".") if parts else "A deliberately mixed room: different backgrounds, new perspectives."
    icebreaker = next((_ICEBREAKERS[t] for t in shared if t in _ICEBREAKERS), None)
    return RoomIntro(why=why, icebreaker=icebreaker or random.Random(seed).choice(_GENERIC))


class HostAgent:
    def __init__(self, llm: LLM):
        self.llm = llm

    def introduce(self, members: list[Attendee], seed: int = 0) -> RoomIntro:
        lines = "\n".join(
            # Only profile fields go to the model, never the raw sign-up text or contact.
            f"- {m.nickname}: {m.profile.role.value}; interests {', '.join(m.profile.interests) or 'none listed'}; "
            f"wants to {', '.join(g.value for g in m.profile.goals)}; \"{m.profile.one_liner}\""
            for m in members
        )
        shared = ", ".join(shared_interests(members)) or "none"
        intro = self.llm.structured(PROMPT.format(members=lines, shared=shared), RoomIntro)
        return intro or intro_offline(members, seed)
