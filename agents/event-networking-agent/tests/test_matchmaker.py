from itertools import combinations

import pytest

from networking_agent.matchmaker import Matchmaker, pair_key, random_rooms, room_quality, room_sizes
from networking_agent.synthetic import make_attendees


def profiles(n, seed=0):
    return {f"a{i:03d}": s.truth for i, s in enumerate(make_attendees(n, seed))}


@pytest.mark.parametrize("n", range(0, 60))
def test_room_sizes_are_balanced(n):
    sizes = room_sizes(n, 5)
    assert sum(sizes) == n
    if n:
        assert max(sizes) <= 5
        assert max(sizes) - min(sizes) <= 1


def test_room_sizes_examples():
    assert room_sizes(250, 5) == [5] * 50
    assert room_sizes(7, 5) == [4, 3]
    assert room_sizes(3, 5) == [3]


def test_everyone_placed_exactly_once():
    p = profiles(103)
    groups = Matchmaker(5).group(p)
    placed = [a for g in groups for a in g]
    assert sorted(placed) == sorted(p)


def test_beats_random_grouping():
    p = profiles(250)
    mm = room_quality(Matchmaker(5).group(p), p)
    rnd = room_quality(random_rooms(list(p), 5), p)
    assert mm["mean_pair_affinity"] > 2 * rnd["mean_pair_affinity"]
    assert mm["share_with_goal_match"] > rnd["share_with_goal_match"]


def test_no_repeat_pairs_when_avoidable():
    p = profiles(100)
    met = set()
    for r in range(3):
        for g in Matchmaker(5, seed=r).group(p, met):
            pairs = {pair_key(a, b) for a, b in combinations(g, 2)}
            assert not pairs & met
            met |= pairs


def test_deterministic_for_same_seed():
    p = profiles(60)
    assert Matchmaker(5, seed=7).group(p) == Matchmaker(5, seed=7).group(p)
