from secure_agent_harness.memory import MemoryStore


def test_memory_is_scoped_by_user(tmp_path):
    memory = MemoryStore(tmp_path / "memory.sqlite3")
    memory.remember("alice", "Prefers Python")
    memory.remember("bob", "Prefers Java")
    assert memory.recent("alice") == ["Prefers Python"]
    assert memory.recent("bob") == ["Prefers Java"]


def test_memory_limit_and_clear(tmp_path):
    memory = MemoryStore(tmp_path / "memory.sqlite3")
    for i in range(105):
        memory.remember("alice", f"fact-{i}")
    facts = memory.recent("alice", 20)
    assert len(facts) == 20
    assert facts[0] == "fact-104"
    memory.clear("alice")
    assert memory.recent("alice") == []
