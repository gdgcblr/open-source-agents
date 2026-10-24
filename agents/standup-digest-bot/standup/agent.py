"""The standup agent: turn an ActivityLog into a trustworthy Digest.

Pipeline:  ActivityLog  ->  prompt  ->  LLM  ->  verify + guardrail  ->  Digest

Two properties the judges asked for are enforced here *in code*, not left to the
model's goodwill:

1. Anti-hallucination guardrail
   The model is told to cite an [event_id] for every bullet. After generation we
   scan each bullet: if it references an id that is not in the real activity log
   (or references nothing at all), we do not trust it. The bullet is rewritten
   into a ``[confirm: ...]`` placeholder so a human can verify, rather than
   letting an unsupported claim ship as fact.

2. Escalation / when-not-to-act
   The agent refuses to confidently produce a digest when it has no business
   doing so: no activity found, a partial fetch (a data source failed), or too
   many claims ended up needing confirmation. In those cases it still returns a
   best-effort draft but sets ``escalate=True`` with reasons, so the caller
   hands off to a human instead of auto-posting.
"""

from __future__ import annotations

import json
import logging
import re

from .llm import LLMProvider
from .models import ActivityLog, Digest

logger = logging.getLogger(__name__)

# If more than this share of generated bullets are unsupported, the draft is not
# trustworthy enough to post unattended.
_CONFIRM_ESCALATION_RATIO = 0.5

SYSTEM_PROMPT = """\
You are a terse engineering standup assistant. You convert a developer's real
GitHub activity into a daily standup update.

HARD RULES:
1. You may ONLY describe work that appears in the EVIDENCE list below.
2. Every bullet MUST begin with the exact [event_id] it is based on, copied
   verbatim from EVIDENCE (e.g. "[commit:abc1234] ...").
3. NEVER invent work, progress, numbers, or outcomes not present in EVIDENCE.
4. If you are unsure or lack evidence for something, do not guess.
5. Keep each bullet to one short sentence, past tense, plain language.

Respond with ONLY a JSON object of this shape (no markdown, no prose):
{"yesterday": ["[id] ..."], "today": ["..."], "blockers": ["..."]}
The "today" and "blockers" arrays may contain planning notes without ids.
"""

# Matches a leading [event_id] token, tolerating an optional "-"/"*" bullet
# marker a model may prepend (e.g. "- [commit:abc] ...").
_ID_RE = re.compile(r"^\s*[-*]?\s*\[([^\]]+)\]")


class StandupAgent:
    def __init__(self, llm: LLMProvider):
        self.llm = llm

    def generate(self, log: ActivityLog) -> Digest:
        reasons: list[str] = []

        # --- Pre-flight escalation checks (when NOT to act) ----------------
        if log.is_empty():
            reasons.append(
                "No tracked GitHub activity was found for this day, so there is "
                "nothing to ground a report on."
            )
        if log.partial:
            reasons.append(
                "One or more activity sources failed to load; the picture may be "
                "incomplete: " + "; ".join(log.fetch_warnings)
            )

        if log.is_empty():
            # Nothing real to summarize. Return an explicit escalation draft
            # rather than inventing a plausible-sounding update.
            text = _render_markdown(
                yesterday=["[confirm: no tracked activity found for this day]"],
                today=["[confirm: add today's plan]"],
                blockers=[],
            )
            return Digest(
                text=text,
                escalate=True,
                escalation_reasons=reasons,
                needs_confirmation=["no tracked activity found for this day"],
            )

        # --- Generate -------------------------------------------------------
        user_prompt = _build_user_prompt(log)
        raw = self.llm.complete(SYSTEM_PROMPT, user_prompt)
        parsed = _parse_json(raw)

        # --- Verify + enforce guardrail ------------------------------------
        valid_ids = log.event_ids
        yesterday, referenced, confirm_items = _verify_bullets(
            parsed.get("yesterday", []), valid_ids
        )
        today = _sanitize_plain(parsed.get("today", []))
        blockers = _sanitize_plain(parsed.get("blockers", []))

        # Escalate if the model leaned on fabrication.
        total = max(len(yesterday), 1)
        if confirm_items and (len(confirm_items) / total) >= _CONFIRM_ESCALATION_RATIO:
            reasons.append(
                f"{len(confirm_items)} of {total} reported items could not be "
                "matched to real activity and need human confirmation."
            )

        text = _render_markdown(yesterday, today, blockers)
        return Digest(
            text=text,
            escalate=bool(reasons),
            escalation_reasons=reasons,
            needs_confirmation=confirm_items,
            referenced_event_ids=referenced,
        )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _build_user_prompt(log: ActivityLog) -> str:
    evidence = "\n".join(e.as_evidence_line() for e in log.events)
    return (
        f"Developer: {log.username}\n"
        f"Date: {log.date}\n\n"
        f"EVIDENCE (the only facts you may use):\n{evidence}\n"
    )


def _parse_json(raw: str) -> dict:
    """Best-effort JSON extraction; tolerant of models that wrap in prose/fences."""
    raw = raw.strip()
    # Strip ```json ... ``` fences if present.
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to locate the first {...} block.
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    logger.warning("LLM output was not valid JSON; treating as unsupported.")
    return {"yesterday": [], "today": [], "blockers": []}


def _verify_bullets(
    bullets: list, valid_ids: set[str]
) -> tuple[list[str], set[str], list[str]]:
    """Enforce the grounding guardrail on 'yesterday' bullets.

    Returns (clean_bullets, referenced_ids, confirm_items).
    A bullet that cites a real id is kept. A bullet that cites nothing or an
    unknown id is converted into a [confirm: ...] placeholder.
    """
    clean: list[str] = []
    referenced: set[str] = set()
    confirm_items: list[str] = []

    for bullet in bullets:
        if not isinstance(bullet, str) or not bullet.strip():
            continue
        text = bullet.strip()
        m = _ID_RE.match(text)
        if m and m.group(1) in valid_ids:
            referenced.add(m.group(1))
            clean.append(text)
        else:
            # Unsupported claim -> quarantine it behind a confirmation flag.
            stripped = _ID_RE.sub("", text).strip() or text
            note = f"[confirm: unverified - {stripped}]"
            clean.append(note)
            confirm_items.append(stripped)

    return clean, referenced, confirm_items


def _sanitize_plain(items: list) -> list[str]:
    return [str(i).strip() for i in items if isinstance(i, str) and i.strip()]


def _render_markdown(
    yesterday: list[str], today: list[str], blockers: list[str]
) -> str:
    def block(title: str, items: list[str]) -> str:
        if not items:
            return f"**{title}:**\n- (none)"
        body = "\n".join(f"- {i.lstrip('- ').strip()}" for i in items)
        return f"**{title}:**\n{body}"

    return "\n\n".join(
        [
            block("Yesterday", yesterday),
            block("Today", today),
            block("Blockers", blockers),
        ]
    )
