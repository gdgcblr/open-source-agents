from networking_agent.llm import LLM
from networking_agent.models import Goal, Role
from networking_agent.profile_agent import ProfileAgent, _clean, _Draft, extract_offline


def test_offline_extraction():
    p = extract_offline("Backend engineer building AI agents on GCP. We're hiring!")
    assert p.role == Role.developer
    assert {"agents", "cloud"} <= set(p.interests)
    assert p.goals == [Goal.hire]


def test_machine_learning_is_not_a_learning_goal():
    p = extract_offline("Engineer working on machine learning infra.")
    assert Goal.learn not in p.goals


def test_defaults_to_network_goal():
    assert extract_offline("Hello!").goals == [Goal.network]


def test_clean_drops_unknown_interests_and_caps_lengths():
    draft = _Draft(
        role=Role.student,
        interests=["Agents", "quantum basket weaving", "agents", "rag", "web", "data", "cloud", "mobile"],
        goals=[Goal.learn, Goal.learn],
        one_liner=" ".join(["word"] * 40),
    )
    p = _clean(draft)
    assert p.interests == ["agents", "rag", "web", "data", "cloud"]
    assert p.goals == [Goal.learn]
    assert len(p.one_liner.split()) == 15


def test_agent_falls_back_offline_without_key():
    p = ProfileAgent(LLM(mode="offline")).build("Student who wants to learn about RAG")
    assert p.role == Role.student
    assert "rag" in p.interests
    assert Goal.learn in p.goals
