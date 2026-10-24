"""Synthetic attendees for the simulator and tests.

Each one has a ground-truth profile and a free-text sign-up written from it, so the
profile agent can be checked against what the "attendee" actually meant. The text is
phrased naturally on purpose: the offline keyword extractor gets some of it wrong.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .models import Goal, Profile, Role

_ROLE_WEIGHTS = {
    Role.student: 32,
    Role.developer: 38,
    Role.designer: 6,
    Role.researcher: 8,
    Role.founder: 8,
    Role.product: 8,
}
_ROLE_PHRASES = {
    Role.student: ["Final year B.Tech student", "CS student at a college in Bengaluru", "Undergrad, second year"],
    Role.developer: ["Software engineer", "Backend developer", "Engineer at a mid-size company"],
    Role.designer: ["Product designer", "UX designer at an agency"],
    Role.researcher: ["PhD student", "Research engineer at a lab"],
    Role.founder: ["Founder of an early-stage startup", "Building my own startup as a solo founder"],
    Role.product: ["Product manager", "PM at a SaaS company"],
}
_ROLE_IMPLIES = {Role.designer: "design", Role.founder: "startups", Role.researcher: "research"}
_ROLE_GOALS = {
    Role.student: [Goal.learn, Goal.get_hired, Goal.collaborate, Goal.network],
    Role.developer: [Goal.collaborate, Goal.mentor, Goal.get_hired, Goal.network, Goal.hire],
    Role.designer: [Goal.collaborate, Goal.get_hired, Goal.network],
    Role.researcher: [Goal.collaborate, Goal.mentor, Goal.network],
    Role.founder: [Goal.hire, Goal.cofounder, Goal.network],
    Role.product: [Goal.network, Goal.collaborate, Goal.hire],
}
_INTEREST_WEIGHTS = {
    "agents": 3, "llms": 3, "rag": 2, "cloud": 2, "web": 2, "data": 1.5, "mobile": 1,
    "devops": 1, "mlops": 1, "computer-vision": 1, "security": 0.7, "design": 0.7,
    "startups": 1, "open-source": 1, "research": 0.7, "gamedev": 0.5, "fintech": 0.7,
    "healthtech": 0.5, "edtech": 0.5,
}  # fmt: skip
_INTEREST_PHRASES = {
    "agents": ["building AI agents", "agentic workflows with ADK", "multi-agent systems"],
    "llms": ["working with LLMs", "prompting Gemini", "GenAI apps"],
    "rag": ["RAG pipelines", "vector search"],
    "mlops": ["MLOps", "model serving"],
    "computer-vision": ["computer vision", "image models"],
    "data": ["data engineering", "analytics and SQL"],
    "web": ["web apps in React", "full-stack web"],
    "mobile": ["Flutter apps", "Android development"],
    "cloud": ["GCP", "serverless on Cloud Run"],
    "devops": ["Kubernetes", "CI/CD and Terraform"],
    "security": ["application security", "infosec"],
    "design": ["UX design", "design systems"],
    "startups": ["startups", "early-stage products"],
    "open-source": ["open source", "maintaining an OSS library"],
    "research": ["reading ML papers", "research"],
    "gamedev": ["game dev in Unity", "indie games"],
    "fintech": ["fintech", "UPI and payments"],
    "healthtech": ["health tech", "medical AI"],
    "edtech": ["edtech", "teaching kids to code"],
}
_GOAL_PHRASES = {
    Goal.learn: ["Here to learn.", "New to AI and want to learn more."],
    Goal.mentor: ["Happy to mentor folks.", "Glad to guide beginners."],
    Goal.hire: ["We're hiring!", "Looking for engineers to join my team."],
    Goal.get_hired: ["Looking for a job.", "Open to work.", "Looking for an internship."],
    Goal.cofounder: ["Looking for a co-founder.", "Want to meet a potential cofounder."],
    Goal.collaborate: ["Want to find teammates for hackathons.", "Looking for collaborators."],
    Goal.network: ["Just here to meet people.", "Curious to meet new folks."],
}
_ADJECTIVES = ["pixel", "quiet", "rapid", "lucid", "cosmic", "sunny", "brave", "nimble", "witty", "mellow"]
_ANIMALS = ["panda", "otter", "falcon", "lynx", "koala", "gecko", "heron", "tiger", "yak", "orca"]


@dataclass
class SyntheticAttendee:
    nickname: str
    about: str
    truth: Profile


def make_attendee(rng: random.Random, index: int) -> SyntheticAttendee:
    role = rng.choices(list(_ROLE_WEIGHTS), weights=list(_ROLE_WEIGHTS.values()))[0]

    tags, weights = list(_INTEREST_WEIGHTS), list(_INTEREST_WEIGHTS.values())
    interests: list[str] = []
    k = rng.randint(2, 4)
    while len(interests) < k:
        tag = rng.choices(tags, weights=weights)[0]
        if tag not in interests:
            interests.append(tag)
    implied = _ROLE_IMPLIES.get(role)
    if implied and implied not in interests:
        interests.insert(0, implied)

    goals = rng.sample(_ROLE_GOALS[role], k=rng.choice([1, 1, 2]))

    topics = [rng.choice(_INTEREST_PHRASES[t]) for t in interests if t != implied]
    topic_text = ", ".join(topics[:-1]) + (" and " if len(topics) > 1 else "") + topics[-1] if topics else "tech"
    about = f"{rng.choice(_ROLE_PHRASES[role])}. Into {topic_text}. " + " ".join(rng.choice(_GOAL_PHRASES[g]) for g in goals)

    nickname = f"{rng.choice(_ADJECTIVES)}-{rng.choice(_ANIMALS)}-{index:03d}"
    return SyntheticAttendee(nickname, about, Profile(role=role, interests=interests, goals=goals))


def make_attendees(n: int, seed: int = 0) -> list[SyntheticAttendee]:
    rng = random.Random(seed)
    return [make_attendee(rng, i) for i in range(n)]
