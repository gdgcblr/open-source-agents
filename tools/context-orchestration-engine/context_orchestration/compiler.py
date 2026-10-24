"""The Context Compiler: canonical state in, a bounded briefing out.

It never dumps state into a prompt. Sections are filled in a fixed priority
order until the token budget is spent, measured against the rendered text
rather than a sum of estimates. Inside a section, items are ranked by
relevance to the assigned task and objective blended with recency, under a
per-section cap.

Anchoring: the earliest decisions and failed attempts are always kept first.
Without it, relevance plus recency quietly drops founding choices ("use
PostgreSQL") in favour of recent detail, and a later reviewer audits work
whose foundations it cannot see.

Whatever does not fit is reported in ``omitted_sections`` and
``dropped_items`` rather than silently vanishing. The assigned task and the
objective are never dropped; if they alone exceed the budget they are
truncated.
"""

from __future__ import annotations

import math
import re
from typing import Protocol

from context_orchestration.contracts import ContextPackage, ExecutionState

WORD = re.compile(r"[a-z0-9]{3,}")
STOP = frozenset(
    "the and for with from that this into its are was were has have will "
    "current state continue execution".split()
)


def words(text: str) -> set[str]:
    return {w for w in WORD.findall(text.lower()) if w not in STOP}


class TokenEstimator(Protocol):
    def count(self, text: str) -> int: ...


class HeuristicTokenEstimator:
    """``max(words, ceil(chars / 4))``. Cheap and dependency-free, not exact."""

    def count(self, text: str) -> int:
        if not text:
            return 0
        return max(len(text.split()), math.ceil(len(text) / 4))


class ContextCompiler:
    def __init__(
        self,
        budget: int = 1200,
        estimator: TokenEstimator | None = None,
        per_section_cap: int = 8,
        anchors: int = 2,
        recency_weight: float = 0.3,
    ) -> None:
        self.budget = budget
        self.estimator = estimator or HeuristicTokenEstimator()
        self.cap = per_section_cap
        self.anchors = anchors
        self.recency_weight = recency_weight

    # -- public ------------------------------------------------------------------

    def compile(self, state: ExecutionState, assigned_task: str, worker_id: str) -> ContextPackage:
        focus = words(assigned_task) | words(state.objective)
        dropped = 0

        def rank(items: list[str], anchored: bool = False) -> list[str]:
            nonlocal dropped
            ranked = self._rank(items, focus, anchored)
            dropped += len(items) - len(ranked)
            return ranked

        issues = [
            f"[{i.severity}] {i.id}: {i.description}"
            + (f" (resolution claimed by {i.resolution_claimed_by}, unverified)"
               if i.resolution_claimed_by else "")
            for i in state.open_issues()
        ]
        notes_title = "NOTES FROM PREVIOUS WORKER" + (
            f" ({state.previous_worker})" if state.previous_worker else ""
        )
        sections: list[tuple[str, list[str], bool]] = [
            ("YOUR ASSIGNED TASK", [assigned_task], True),
            ("TASK OBJECTIVE", [state.objective], True),
            ("CURRENT PROGRESS", [state.current_progress], False),
            ("IMPORTANT DECISIONS", rank(
                [d.decision + (f". Reason: {d.reason}" if d.reason else "") for d in state.decisions],
                anchored=True), False),
            ("COMPLETED WORK", rank(list(state.completed_tasks)), False),
            ("ARTIFACTS", rank(
                [f"{a.name} v{a.version}" + (f" - {a.description}" if a.description else "")
                 + ("" if a.verified else " [unverified]") for a in state.artifacts]), False),
            ("UNRESOLVED ISSUES", rank(issues), False),
            ("FAILED ATTEMPTS (DO NOT REPEAT)", rank(
                [f.approach + (f" - {f.reason}" if f.reason else "") for f in state.failed_attempts],
                anchored=True), False),
            ("ASSUMPTIONS", rank(
                [a.text + (f" ({a.reason})" if a.reason else "") for a in state.assumptions]), False),
            ("LAST ACTION", [state.last_action], False),
            ("RECOMMENDED NEXT ACTION", [state.next_action], False),
            (notes_title, [state.notes_from_previous], False),
        ]

        parts: list[tuple[str, list[str]]] = []
        included: list[str] = []
        omitted: list[str] = []
        for title, items, required in sections:
            items = [i.strip() for i in items if i and i.strip()]
            if not items:
                continue
            if required:
                parts.append((title, [self._fit(parts, title, items[0])]))
                included.append(title)
                continue
            kept: list[str] = []
            for item in items:
                if self._tokens(parts + [(title, kept + [item])]) <= self.budget:
                    kept.append(item)
                else:
                    dropped += 1
            if kept:
                parts.append((title, kept))
                included.append(title)
            else:
                omitted.append(title)

        text = self.render(parts)
        return ContextPackage(
            task_id=state.task_id,
            turn=state.turn + 1,
            target_worker_id=worker_id,
            assigned_task=assigned_task,
            rendered_text=text,
            estimated_tokens=self.estimator.count(text),
            budget=self.budget,
            sections=included,
            omitted_sections=omitted,
            dropped_items=dropped,
        )

    @staticmethod
    def render(parts: list[tuple[str, list[str]]]) -> str:
        return "\n\n".join(
            title + "\n" + "\n".join(f"- {item}" for item in items) for title, items in parts
        )

    # -- internals ---------------------------------------------------------------

    def _tokens(self, parts) -> int:
        return self.estimator.count(self.render(parts))

    def _fit(self, parts, title: str, item: str) -> str:
        """Truncate a required item until the package fits, as a last resort."""
        tokens = item.split()
        candidate = item
        while tokens and self._tokens(parts + [(title, [candidate])]) > self.budget:
            tokens = tokens[: max(1, int(len(tokens) * 0.9))] if len(tokens) > 1 else []
            candidate = " ".join(tokens) + " ..."
        return candidate if tokens else item.split()[0] + " ..."

    def _rank(self, items: list[str], focus: set[str], anchored: bool) -> list[str]:
        if not items:
            return []
        n = len(items)
        head = list(range(min(self.anchors, n))) if anchored else []

        def score(i: int) -> float:
            w = words(items[i])
            relevance = len(w & focus) / len(w) if w else 0.0
            recency = (i + 1) / n
            return (1 - self.recency_weight) * relevance + self.recency_weight * recency

        rest = sorted((i for i in range(n) if i not in head), key=score, reverse=True)
        chosen = (head + rest)[: self.cap]
        return [items[i] for i in chosen]
