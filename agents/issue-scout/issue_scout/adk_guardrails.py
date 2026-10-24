"""ADK callbacks that enforce Issue Scout's guardrails around the model.

Prompts ask the model to behave; these callbacks check that it did:
- `limit_tool_calls` (before_tool): at most MAX_TOOL_CALLS_PER_TURN tool calls per user turn,
  so a confused model cannot loop or burn the GitHub rate limit.
- `remember_tool_urls` (after_tool): records every GitHub URL a tool returned this session.
- `check_model_output` (after_model): masks secrets in the reply and flags any GitHub link that
  neither a tool nor the user supplied, so invented issue links never pass silently.
- `ground_brief`: drops brief file suggestions that are not in the gathered facts.
"""

from typing import Any, Dict, Iterable, Optional

from .conventions import mentioned_paths
from .guardrails import github_urls, redact_secrets, redact_tree, ungrounded_urls

MAX_TOOL_CALLS_PER_TURN = 6
MAX_REMEMBERED_URLS = 2000
BUDGET_KEY = "issue_scout:tool_budget"
GROUNDED_KEY = "issue_scout:grounded_urls"
UNVERIFIED_NOTE = "\n\n> Note from Issue Scout: these links were not in any GitHub data from this session; check them before trusting them: "


def _remember(state, urls: Iterable[str]) -> None:
    known = list(state.get(GROUNDED_KEY) or [])
    new = [url for url in urls if url not in known]
    if new:
        state[GROUNDED_KEY] = (known + new)[-MAX_REMEMBERED_URLS:]


def limit_tool_calls(tool, args: Dict[str, Any], tool_context) -> Optional[Dict[str, Any]]:
    budget = tool_context.state.get(BUDGET_KEY) or {}
    if budget.get("invocation") != tool_context.invocation_id:
        budget = {"invocation": tool_context.invocation_id, "calls": 0}
    if budget["calls"] >= MAX_TOOL_CALLS_PER_TURN:
        return {
            "error": "Tool budget for this turn reached (%d calls). Answer with what you already have "
            "and ask the user before looking up more." % MAX_TOOL_CALLS_PER_TURN
        }
    budget["calls"] += 1
    tool_context.state[BUDGET_KEY] = budget
    return None


def remember_tool_urls(tool, args: Dict[str, Any], tool_context, tool_response: Dict[str, Any]) -> None:
    _remember(tool_context.state, github_urls(tool_response))
    return None


def check_model_output(callback_context, llm_response):
    content = llm_response.content
    if getattr(llm_response, "partial", False) or not content or not content.parts:
        return None
    user = callback_context.user_content
    user_text = "".join(part.text or "" for part in (user.parts if user and user.parts else []))
    _remember(callback_context.state, github_urls(user_text))
    allowed = callback_context.state.get(GROUNDED_KEY) or []

    changed = False
    for part in content.parts:
        if not part.text or getattr(part, "thought", False):
            continue
        text = redact_secrets(part.text)
        unverified = ungrounded_urls(text, allowed)
        if unverified:
            text += UNVERIFIED_NOTE + ", ".join(unverified)
        if text != part.text:
            part.text = text
            changed = True
    return llm_response if changed else None


def ground_brief(brief: Dict[str, Any], facts: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only file suggestions that the facts support; report the rest instead of hiding them."""
    allowed = {entry.get("path", "") for entry in facts.get("likely_files") or []}
    issue = facts.get("issue") or {}
    named = mentioned_paths("%s\n%s" % (issue.get("title", ""), issue.get("body", "")))
    kept, dropped = [], []
    for hint in brief.get("likely_files") or []:
        path = str(hint.get("path", "")).strip()
        if path.startswith("./"):
            path = path[2:]
        if path in allowed or any(path.endswith(name) for name in named):
            kept.append(dict(hint, path=path))
        elif path:
            dropped.append(path)
    brief["likely_files"] = kept
    if dropped:
        brief["dropped_files"] = dropped
    return redact_tree(brief)
