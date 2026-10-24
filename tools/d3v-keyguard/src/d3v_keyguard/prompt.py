"""Out-of-band secure input: never through the LLM chat.

GUI mode runs a tkinter dialog in an isolated subprocess (thread-safe under async
servers like `adk web`); TTY mode uses getpass. KEYGUARD_PROMPT=auto|gui|tty.
A deliberate cancel is final; only an *unavailable* GUI falls back to the terminal.
"""

from __future__ import annotations

import getpass
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Protocol

from .errors import PromptCancelled, PromptUnavailable

MAX_REASON = 200
_HELPER = Path(__file__).with_name("_prompt_helper.py")
_HELPER_ENV = ("SYSTEMROOT", "PATH", "DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "TCL_LIBRARY", "TK_LIBRARY",
               "HOME", "USERPROFILE", "LOCALAPPDATA", "TEMP", "TMP")
DECISIONS = ("approve", "reject", "later")


HIDDEN = "[... {n} chars hidden - do not approve unless you expected this ...]"
MAX_ITEMS = 40  # arguments / argv elements shown individually in a consent dialog
# Argument names that usually decide where a secret goes: shown first in consent dialogs.
_DESTINATION_KEYS = ("url", "uri", "host", "endpoint", "server", "domain", "address", "base_url", "to",
                     "target", "destination", "cmd", "command", "path", "method")


def sanitize(text: str | None, limit: int = MAX_REASON) -> str:
    """Printable-only text, cut to `limit` chars with a visible marker (never silently)."""
    text = "".join(ch if ch.isprintable() else " " for ch in (text or ""))
    if len(text) <= limit:
        return text
    return text[:limit] + " " + HIDDEN.format(n=len(text) - limit)


def clip(text: str | None, limit: int = 300) -> str:
    """Like sanitize, but keeps the head AND the tail (where a destination is often appended)."""
    text = sanitize(text, 10**9)
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]} {HIDDEN.format(n=len(text) - 2 * half)} {text[-half:]}"


def _key_order(item: tuple[str, str]) -> tuple[int, str]:
    key, shown = item
    k = key.lower()
    if k in _DESTINATION_KEYS or any(k.endswith("_" + d) for d in _DESTINATION_KEYS):
        return 0, k
    return (1 if "keyguard://" in shown else 2), k


def describe_args(args: dict) -> list[str]:
    """One consent line per argument: destination-like names first, then handle-bearing ones.

    Values are the model's arguments (handles only, never secret values). Nothing is cut
    without a visible marker.
    """
    shown = [(str(k), json.dumps(v, ensure_ascii=False, default=str)) for k, v in (args or {}).items()]
    shown.sort(key=_key_order)
    lines = [f"  {clip(k, 60)} = {clip(v)}" for k, v in shown[:MAX_ITEMS]]
    if len(shown) > MAX_ITEMS:
        lines.append(f"  [... {len(shown) - MAX_ITEMS} more arguments hidden - do not approve unless you expected this]")
    return lines or ["  (no arguments)"]


def describe_argv(exe: str, argv: list[str]) -> list[str]:
    """One consent line per argv element, with the resolved program path first."""
    lines = [f"  program: {clip(exe, 400)}"]
    lines += [f"  arg {i}: {clip(a)}" for i, a in enumerate(argv[:MAX_ITEMS], 1)]
    if len(argv) > MAX_ITEMS:
        lines.append(f"  [... {len(argv) - MAX_ITEMS} more arguments hidden - do not approve unless you expected this]")
    return lines


class PromptProvider(Protocol):
    def ask_secret(self, title: str, message: str) -> str: ...

    def confirm(self, title: str, message: str) -> bool: ...

    # Optional: review(title, message, items) -> {name: "approve"|"reject"|"later"}


def _tty() -> bool:
    try:
        return sys.stdin.isatty() and sys.stderr.isatty()
    except (AttributeError, ValueError):
        return False


def _read(fn, prompt: str) -> str:
    """Ctrl+C / EOF at a terminal prompt is a cancel, not a traceback."""
    try:
        return fn(prompt)
    except (KeyboardInterrupt, EOFError):
        print("", file=sys.stderr)
        raise PromptCancelled("cancelled") from None


class TtyPrompt:
    def ask_secret(self, title: str, message: str) -> str:
        if not _tty():
            raise PromptUnavailable("no interactive terminal available for secure input")
        print(f"\n[{title}]\n{message}", file=sys.stderr)
        value = _read(getpass.getpass, "> ")
        if not value:
            raise PromptCancelled("cancelled")
        return value

    def confirm(self, title: str, message: str) -> bool:
        if not _tty():
            return False
        print(f"\n[{title}]\n{message}", file=sys.stderr)
        try:
            return _read(input, "Approve? [y/N] ").strip().lower() in ("y", "yes")
        except PromptCancelled:
            return False

    def review(self, title: str, message: str, items: list[dict]) -> dict[str, str]:
        if not _tty():
            return {}
        print(f"\n[{title}]\n{message}", file=sys.stderr)
        out = {}
        for item in items:
            print(f"\n  {item['label']}", file=sys.stderr)
            try:
                answer = _read(input, "  [a]pprove / [r]eject / [L]ater? ").strip().lower()
            except PromptCancelled:
                return out  # undecided entries stay pending
            out[item["name"]] = {"a": "approve", "approve": "approve", "r": "reject", "reject": "reject"}.get(
                answer, "later")
        return out


class GuiPrompt:
    def __init__(self, timeout: float = 300):
        self.timeout = timeout

    def _run(self, request: dict) -> dict:
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(_HELPER)],
                input=json.dumps(request),
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env={k: v for k, v in os.environ.items() if k in _HELPER_ENV},
            )
        except subprocess.TimeoutExpired:
            raise PromptCancelled("secure prompt timed out") from None
        except OSError:
            raise PromptUnavailable("secure prompt helper could not be started") from None
        try:
            reply = json.loads(proc.stdout) if proc.returncode == 0 else None
        except ValueError:
            reply = None
        if not isinstance(reply, dict):
            raise PromptUnavailable("GUI dialog unavailable (tkinter or display missing)")
        if reply.get("cancelled"):
            raise PromptCancelled("cancelled")
        return reply

    def ask_secret(self, title: str, message: str) -> str:
        value = self._run({"kind": "secret", "title": title, "message": message}).get("value")
        if not value:
            raise PromptCancelled("cancelled")
        return value

    def confirm(self, title: str, message: str) -> bool:
        try:
            return bool(self._run({"kind": "confirm", "title": title, "message": message}).get("ok"))
        except PromptUnavailable:
            raise
        except PromptCancelled:
            return False

    def review(self, title: str, message: str, items: list[dict]) -> dict[str, str]:
        try:
            reply = self._run({"kind": "review", "title": title, "message": message, "items": items[:50]})
        except PromptUnavailable:
            raise
        except PromptCancelled:
            return {}
        decisions = reply.get("decisions")
        return {k: v for k, v in decisions.items() if v in DECISIONS} if isinstance(decisions, dict) else {}


class AutoPrompt:
    """GUI dialog first; falls back to a hidden terminal prompt only if the GUI is unavailable."""

    def __init__(self):
        self._gui, self._tty = GuiPrompt(), TtyPrompt()

    def ask_secret(self, title: str, message: str) -> str:
        try:
            return self._gui.ask_secret(title, message)
        except PromptUnavailable:
            if not _tty():
                raise
            return self._tty.ask_secret(title, message)

    def confirm(self, title: str, message: str) -> bool:
        try:
            return self._gui.confirm(title, message)
        except PromptUnavailable:
            return self._tty.confirm(title, message)

    def review(self, title: str, message: str, items: list[dict]) -> dict[str, str]:
        try:
            return self._gui.review(title, message, items)
        except PromptUnavailable:
            return self._tty.review(title, message, items)


def default_prompt() -> PromptProvider:
    mode = os.environ.get("KEYGUARD_PROMPT", "auto").lower()
    if mode == "gui":
        return GuiPrompt()
    if mode == "tty":
        return TtyPrompt()
    return AutoPrompt()


def describe_pending(item: dict) -> str:
    """One-line description of a pending entry for the human reviewer (masked preview only)."""
    meta = item.get("metadata", {})
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(item.get("created") or 0))
    parts = [f"{item['name']}  {item['preview']}  stored {when}"]
    if meta.get("captured_from"):
        parts.append(f"captured from tool '{sanitize(meta['captured_from'], 60)}' (unverified)")
    if meta.get("description"):
        parts.append(f"description (unverified): {sanitize(meta['description'], 120)}")
    if item.get("replaces"):
        same = item.get("same_as_current")
        parts.append("!! REPLACES an existing ACTIVE secret"
                     + {True: " (identical value)", False: " with a DIFFERENT value"}.get(same, ""))
    if not item.get("valid", True):
        parts.append("!! failed integrity checks - reject it")
    return " | ".join(parts)


def review_pending(vault, prompt) -> dict:
    """Show each pending entry to the user and apply their per-entry decision.

    Approval is bound to the exact content the user reviewed (digest), so an entry swapped
    while the dialog is open is not approved.
    """
    items = vault.review_items()
    if not items:
        return {"approved": [], "rejected": [], "pending": []}
    title = "d3v-keyguard: review entries stored while locked"
    intro = ("These entries were stored while the vault was locked (by you, an agent or a tool).\n"
             "Approve only values you recognise. Reject anything unexpected.")
    shown = [{"name": i["name"], "label": describe_pending(i)} for i in items]
    review = getattr(prompt, "review", None)
    if review is not None:
        decisions = review(title, intro, shown)
    else:
        decisions = {s["name"]: "approve" if prompt.confirm(title, intro + "\n\n" + s["label"]) else "later"
                     for s in shown}
    approve = {i["name"]: i["digest"] for i in items if decisions.get(i["name"]) == "approve" and i["valid"]}
    reject = [i["name"] for i in items if decisions.get(i["name"]) == "reject"]
    approved = vault.approve(approve) if approve else []
    rejected = vault.reject(reject) if reject else []
    left = [i["name"] for i in items if i["name"] not in approved and i["name"] not in rejected]
    return {"approved": approved, "rejected": rejected, "pending": left}
