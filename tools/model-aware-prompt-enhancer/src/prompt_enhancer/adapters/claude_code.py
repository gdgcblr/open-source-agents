"""Claude Code ``UserPromptSubmit`` hook adapter (experimental).

Contract, per https://code.claude.com/docs/en/hooks:

* stdin is JSON with the submitted text in ``prompt``.
* The hook cannot replace the prompt. It can add ``additionalContext`` for
  Claude and show ``systemMessage`` to the user; it could also block, which
  this adapter never does.
* The model is not part of the input, so it comes from ``PROMPT_ENHANCER_MODEL``
  / ``ANTHROPIC_MODEL``; otherwise a Claude model is assumed.

It fails open: on any error it prints nothing and exits 0, so the prompt always
reaches Claude unmodified. Only the contract is tested here (unit tests feed it
documented payloads); it has not been verified against every Claude Code version.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, TextIO

from ..engine import enhance


def build_output(payload: dict[str, Any]) -> dict[str, Any] | None:
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or os.environ.get("PROMPT_ENHANCER_DISABLE") == "1":
        return None
    r = enhance(prompt, harness="claude-code")
    if r.status == "skipped":
        return None
    out: dict[str, Any] = {}
    # Restating constraints as hidden context is opt-in, for the same reason structural patches are:
    # live A/B runs showed no gain from restating alone. Diagnostics shown to the user stay on.
    if os.environ.get("PROMPT_ENHANCER_RESTATE") != "1":
        r.additional_context = None
    if r.additional_context:
        out["hookSpecificOutput"] = {"hookEventName": "UserPromptSubmit", "additionalContext": r.additional_context}
    notes: list[str] = []
    if r.additional_context:
        notes.append(f"restated {sum(1 for q in r.analysis.requirements if q.kind == 'constraint')} constraint(s) as context; your prompt was not changed")
    show = os.environ.get("PROMPT_ENHANCER_SHOW_SUGGESTIONS", "1") == "1"
    for d in r.analysis.diagnostics:
        if d.severity == "error" or (show and d.severity == "warning"):
            notes.append(f"{d.rule_id}: {d.message}")
    questions = [p.question for p in r.analysis.patches if p.needs_input and p.question]
    if questions and show:
        notes.append("consider answering: " + " / ".join(questions[:2]))
    if notes:
        out["systemMessage"] = "prompt-enhancer: " + " | ".join(notes[:4])
    return out or None


def main(stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> int:
    try:
        payload = json.load(stdin)
        out = build_output(payload) if isinstance(payload, dict) else None
        if out:
            stdout.write(json.dumps(out))
    except Exception:  # fail open: never block or break the user's prompt
        return 0
    return 0
