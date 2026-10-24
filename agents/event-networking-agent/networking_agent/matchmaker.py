"""Matchmaker: groups attendees into rooms of 4-5 people likely to hit it off.

Deliberately plain code rather than an LLM call: it has to place 250 people in about a
second, give the same answer for the same input, and never seat two people together twice.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from itertools import combinations

from .models import Goal, Profile, Role

# Goal pairs that make a conversation worth having, in either order.
COMPLEMENTARY_GOALS = {
    frozenset({Goal.learn, Goal.mentor}),
    frozenset({Goal.hire, Goal.get_hired}),
    frozenset({Goal.cofounder}),  # cofounder <-> cofounder
    frozenset({Goal.collaborate}),  # collaborate <-> collaborate
}
INTEREST_WEIGHT = 0.6
GOAL_WEIGHT = 0.4
ROLE_BONUS = 0.05  # per distinct role in a room, so rooms are not all students or all founders
REPEAT_PENALTY = 2.0  # larger than any possible affinity, so repeats only happen when unavoidable
GOOD_MATCH = 0.3


def goals_complement(a: Profile, b: Profile) -> bool:
    return any(frozenset({ga, gb}) in COMPLEMENTARY_GOALS for ga in a.goals for gb in b.goals)


def affinity(a: Profile, b: Profile) -> float:
    """0..1 score for how promising a conversation between two people looks."""
    ia, ib = set(a.interests), set(b.interests)
    interest = len(ia & ib) / len(ia | ib) if ia | ib else 0.0
    return INTEREST_WEIGHT * interest + GOAL_WEIGHT * goals_complement(a, b)


def room_sizes(n: int, room_size: int) -> list[int]:
    """Split n people into as few rooms as possible, each of size room_size or room_size - 1
    (smaller only when n itself is that small)."""
    if n == 0:
        return []
    k = math.ceil(n / room_size)
    base, extra = divmod(n, k)
    return [base + 1] * extra + [base] * (k - extra)


def pair_key(a: str, b: str) -> frozenset[str]:
    return frozenset((a, b))


class Matchmaker:
    def __init__(self, room_size: int = 5, seed: int = 0, improve_passes: int = 3):
        self.room_size = room_size
        self.seed = seed
        self.improve_passes = improve_passes

    def group(self, profiles: dict[str, Profile], met: set[frozenset[str]] | None = None) -> list[list[str]]:
        met = met or set()
        ids = sorted(profiles)
        random.Random(self.seed).shuffle(ids)
        n = len(ids)

        score = [[0.0] * n for _ in range(n)]
        for i, j in combinations(range(n), 2):
            s = affinity(profiles[ids[i]], profiles[ids[j]])
            if pair_key(ids[i], ids[j]) in met:
                s -= REPEAT_PENALTY
            score[i][j] = score[j][i] = s
        roles = [profiles[a].role for a in ids]

        groups = self._greedy(score, roles, room_sizes(n, self.room_size))
        self._improve(groups, score, roles)
        return [[ids[i] for i in g] for g in groups]

    @staticmethod
    def _greedy(score: list[list[float]], roles: list[Role], sizes: list[int]) -> list[list[int]]:
        n = len(score)
        good = [{j for j in range(n) if j != i and score[i][j] >= GOOD_MATCH} for i in range(n)]
        unassigned = set(range(n))
        groups = []
        for size in sizes:
            # Seed with whoever has the fewest good options left, so they are not
            # stuck with the leftovers at the end.
            seed = min(unassigned, key=lambda i: (len(good[i] & unassigned), i))
            group = [seed]
            unassigned.discard(seed)
            while len(group) < size:
                present = {roles[m] for m in group}

                def gain(j: int) -> float:
                    mean = sum(score[j][m] for m in group) / len(group)
                    return mean + (ROLE_BONUS if roles[j] not in present else 0.0)

                best = max(sorted(unassigned), key=gain)
                group.append(best)
                unassigned.discard(best)
            groups.append(group)
        return groups

    def _improve(self, groups: list[list[int]], score: list[list[float]], roles: list[Role]) -> None:
        """Local search: swap two people between rooms whenever it raises the total score."""
        role_counts = [Counter(roles[m] for m in g) for g in groups]

        def role_delta(counts: Counter, out: Role, inn: Role) -> int:
            if out == inn:
                return 0
            return (counts[inn] == 0) - (counts[out] == 1)

        for _ in range(self.improve_passes):
            improved = False
            for ga, gb in combinations(range(len(groups)), 2):
                A, B = groups[ga], groups[gb]
                for ia in range(len(A)):
                    for ib in range(len(B)):
                        a, b = A[ia], B[ib]
                        delta = (
                            sum(score[b][m] - score[a][m] for m in A if m != a)
                            + sum(score[a][m] - score[b][m] for m in B if m != b)
                            + ROLE_BONUS * role_delta(role_counts[ga], roles[a], roles[b])
                            + ROLE_BONUS * role_delta(role_counts[gb], roles[b], roles[a])
                        )
                        if delta > 1e-9:
                            A[ia], B[ib] = b, a
                            role_counts[ga][roles[a]] -= 1
                            role_counts[ga][roles[b]] += 1
                            role_counts[gb][roles[b]] -= 1
                            role_counts[gb][roles[a]] += 1
                            improved = True
            if not improved:
                return


def random_rooms(ids: list[str], room_size: int, seed: int = 0) -> list[list[str]]:
    """Baseline for comparison: shuffle and chunk."""
    ids = sorted(ids)
    random.Random(seed).shuffle(ids)
    rooms, start = [], 0
    for size in room_sizes(len(ids), room_size):
        rooms.append(ids[start : start + size])
        start += size
    return rooms


def room_quality(rooms: list[list[str]], profiles: dict[str, Profile]) -> dict[str, float]:
    """Summary numbers used by the simulator and tests to compare groupings."""
    pair_scores, shared, complement = [], set(), set()
    for room in rooms:
        for a, b in combinations(room, 2):
            pa, pb = profiles[a], profiles[b]
            pair_scores.append(affinity(pa, pb))
            if set(pa.interests) & set(pb.interests):
                shared |= {a, b}
            if goals_complement(pa, pb):
                complement |= {a, b}
    n = sum(len(r) for r in rooms) or 1
    return {
        "mean_pair_affinity": sum(pair_scores) / len(pair_scores) if pair_scores else 0.0,
        "share_with_common_interest": len(shared) / n,
        "share_with_goal_match": len(complement) / n,
    }
