"""Namma Commit (Newcomer Coach) command line.

  python -m mergewarden.coach serve [--port 8090]   simulator + leaderboard + Twilio webhook
  python -m mergewarden.coach chat [--user NAME]     terminal simulator (text only)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from . import config


async def _chat(user: str) -> None:
    from .service import default_coach

    coach = default_coach()
    print(f"Namma Commit 🤝 your first PR, in your language (model {config.MODEL}). Type 'quit' to exit, 'help' for commands.\n")
    loop = asyncio.get_running_loop()
    while True:
        try:
            text = await loop.run_in_executor(None, lambda: input("you › "))
        except (EOFError, KeyboardInterrupt):
            break
        if text.strip().lower() in {"quit", "exit"}:
            break
        if not text.strip():
            continue
        _show(await coach.handle_message(f"cli:{user}", text=text, notify=_later))


def _show(r) -> None:
    print(f"\ncoach [{r.language}] › {r.text}")
    if r.review:
        print(f"  🔍 gatekeeper: {r.review['verdict']} · {r.review['score']}/100")
    if r.points_awarded:
        print(f"  ⭐ +{r.points_awarded} points")
    for b in r.badges:
        print(f"  🏅 {b}")
    for a in r.attachments:
        print(f"  📄 {a}")
    print()


async def _later(r) -> None:
    """Gatekeeper review results arrive while the student is typing."""
    print("\n\n(new message)", end="")
    _show(r)
    print("you › ", end="", flush=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="coach", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("serve", help="web simulator, leaderboard and Twilio webhook")
    s.add_argument("--host", default="127.0.0.1",
                   help="bind address (default localhost only; ngrok works with this. Use 0.0.0.0 only on a trusted network)")
    s.add_argument("--port", type=int, default=config.PORT)
    c = sp.add_parser("chat", help="chat with the coach in this terminal")
    c.add_argument("--user", default="local", help="any name; separates conversations")
    a = p.parse_args(argv)
    if a.cmd == "serve":
        from .server import serve
        serve(a.host, a.port)
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
        asyncio.run(_chat(a.user))
    return 0
