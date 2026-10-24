"""Command-line interface: python -m issue_scout <command> ..."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

from .github import GitHubError
from .guardrails import redact_secrets
from .models import BEGINNER_LABELS, Profile
from .report import render_brief, render_candidate, render_find, render_related
from .scout import Scout

PROJECT_DIR = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path) -> None:
    """Load KEY=VALUE lines from a .env file without overriding the real environment."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def _split(values: Optional[List[str]]) -> List[str]:
    items: List[str] = []
    for value in values or []:
        items.extend(part.strip().lower() for part in value.split(",") if part.strip())
    return items


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="issue-scout",
        description="Find open-source issues that are genuinely available, and get a plan to start them.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    find = sub.add_parser("find", help="Shortlist available beginner-friendly issues for you.")
    find.add_argument("--lang", action="append", help="Language(s) you know, e.g. --lang python --lang go or --lang python,go")
    find.add_argument("--user", help="Your GitHub username; languages are inferred from your public repos.")
    find.add_argument("--topic", action="append", help="Repository topic(s) to focus on, e.g. machine-learning")
    find.add_argument("--label", action="append", help='Issue label(s) to search (default: "good first issue", "help wanted")')
    find.add_argument("--hours", type=float, default=3.0, help="Hours you can spend (default: 3)")
    find.add_argument("--limit", type=int, default=5, help="Number of picks to show (default: 5)")
    find.add_argument("--min-stars", type=int, default=100, help="Ignore smaller repos (default: 100)")
    find.add_argument("--max-stars", type=int, help="Ignore bigger repos, e.g. 20000 to avoid giant projects")
    find.add_argument("--show-skipped", action="store_true", help="Also list the dead ends that were filtered out")
    find.add_argument("--json", action="store_true", help="Print JSON instead of Markdown")

    inspect = sub.add_parser("inspect", help="Check if a single issue is still a good pick.")
    inspect.add_argument("issue", help="Issue URL or owner/repo#123")
    inspect.add_argument("--hours", type=float, default=3.0)
    inspect.add_argument("--json", action="store_true")

    related = sub.add_parser("related", help="List related issues and merged PRs for an issue.")
    related.add_argument("issue", help="Issue URL or owner/repo#123")
    related.add_argument("--json", action="store_true")

    brief = sub.add_parser("brief", help="Starter brief: where to look, prior work, house rules, plan.")
    brief.add_argument("issue", help="Issue URL or owner/repo#123")
    brief.add_argument("--hours", type=float, default=3.0)
    brief.add_argument("--no-ai", action="store_true", help="Skip Gemini and print only the gathered facts")
    brief.add_argument("--json", action="store_true")

    sub.add_parser("mcp", help="Run the MCP server over stdio (for Gemini CLI, Claude Code, Cursor...).")
    sub.add_parser("doctor", help="Check Python, dependencies, .env, and that your GitHub and Gemini keys work.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    load_dotenv(PROJECT_DIR / ".env")
    args = build_parser().parse_args(argv)

    if args.command == "mcp":
        from .mcp_server import main as serve

        serve()
        return 0
    if args.command == "doctor":
        return doctor()

    scout = Scout()
    try:
        if args.command == "find":
            return _find(scout, args)
        if args.command == "inspect":
            candidate = scout.inspect(args.issue, Profile(languages=[], hours=args.hours))
            _emit(args, candidate.to_dict(), lambda: render_candidate(candidate, scout.now) + "\n")
            return 0
        if args.command == "related":
            related = scout.related(args.issue)
            data = {key: [vars(item) for item in items] for key, items in related.items()}
            _emit(args, data, lambda: render_related(data))
            return 0
        if args.command == "brief":
            return _brief(scout, args)
    except (GitHubError, ValueError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    return 2


def _find(scout: Scout, args) -> int:
    languages = _split(args.lang)
    topics = _split(args.topic)
    labels = [label.strip() for label in (args.label or []) if label.strip()] or list(BEGINNER_LABELS)
    if args.user and not languages:
        profile = scout.profile_from_user(args.user, topics=topics, hours=args.hours, labels=labels,
                                          min_stars=args.min_stars, max_stars=args.max_stars)
        if not profile.languages:
            print("error: could not infer languages for %s; pass --lang" % args.user, file=sys.stderr)
            return 1
    elif languages:
        profile = Profile(languages=languages, topics=topics, hours=args.hours, labels=labels,
                          min_stars=args.min_stars, max_stars=args.max_stars)
    else:
        print("error: pass --lang (e.g. --lang python) or --user <github-username>", file=sys.stderr)
        return 2
    result = scout.find(profile, limit=args.limit)
    _emit(args, result.to_dict(), lambda: render_find(result, scout.now, args.show_skipped))
    return 0


def _brief(scout: Scout, args) -> int:
    facts = scout.brief_facts(args.issue, Profile(languages=[], hours=args.hours))
    ai = None
    note = ""
    if not args.no_ai:
        try:
            from .agent import api_key_configured, write_brief
        except ImportError:
            note = "Gemini brief skipped: install requirements.txt on Python 3.11+ to enable it."
        else:
            if api_key_configured():
                # ADK logs full tracebacks for model errors; the note below is enough for a CLI user.
                logging.getLogger("google_adk").setLevel(logging.CRITICAL)
                try:
                    ai = write_brief(facts)
                except Exception as exc:  # model or network failure should not lose the facts
                    note = "Gemini brief failed (%s); showing gathered facts only." % _short_error(exc)
            else:
                note = "Gemini brief skipped: set GOOGLE_API_KEY to add a summary and plan."
    if args.json:
        print(redact_secrets(json.dumps({"facts": facts, "ai_brief": ai, "note": note}, indent=2, default=str)))
    else:
        sys.stdout.write(redact_secrets(render_brief(facts, scout.now, ai)))
        if (ai or {}).get("dropped_files"):
            print("\n_Guardrail: removed file suggestions not found in the repo data: %s_" % ", ".join(ai["dropped_files"]))
        if note:
            print("\n_Note: %s_" % note)
    return 0


def doctor() -> int:
    """Check the setup step by step. Read-only; uses no API quota (GitHub /rate_limit and Gemini
    model listing are free). Exit code 0 means the core works; warnings only limit extras."""
    ok, warn, fail = "[ok]  ", "[warn]", "[FAIL]"
    failed = False

    def line(mark, text):
        print("%s %s" % (mark, text))

    version = sys.version_info
    if version >= (3, 11):
        line(ok, "Python %d.%d.%d" % version[:3])
    elif version >= (3, 9):
        line(warn, "Python %d.%d: the CLI core works, but ADK and MCP need 3.11+" % version[:2])
    else:
        line(fail, "Python %d.%d is too old (need 3.9+, recommended 3.11+)" % version[:2])
        failed = True

    for module, purpose in (("google.adk", "Gemini briefs, adk web/run"), ("mcp", "MCP server")):
        try:
            __import__(module)
            line(ok, "%s installed (%s)" % (module, purpose))
        except ImportError:
            line(warn, "%s not installed: run `pip install -r requirements.txt` for %s" % (module, purpose))

    env_file = PROJECT_DIR / ".env"
    line(ok if env_file.is_file() else warn,
         ".env found at %s" % env_file if env_file.is_file() else "no .env (optional): cp .env.example .env")

    client_token = os.environ.get("GITHUB_TOKEN")
    try:
        from .github import GitHubClient

        limits = GitHubClient().get("/rate_limit")["resources"]
        core, search = limits["core"], limits["search"]
        if client_token:
            line(ok, "GitHub token works: %d/%d core requests, %d/%d searches left"
                 % (core["remaining"], core["limit"], search["remaining"], search["limit"]))
        else:
            line(warn, "no GITHUB_TOKEN: anonymous limit %d/%d requests left this hour; code pointers need a token"
                 % (core["remaining"], core["limit"]))
    except GitHubError as exc:
        line(fail, "GitHub check failed: %s" % exc)
        failed = True

    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    model = os.environ.get("ISSUE_SCOUT_MODEL", "gemini-3.5-flash")
    if not key:
        line(warn, "no GOOGLE_API_KEY: Gemini briefs and the chat agent are off; everything else works")
    else:
        try:
            from google import genai

            gemini = genai.Client(api_key=key)  # keep a reference: the pager needs an open client
            names = {m.name.replace("models/", "") for m in gemini.models.list()}
            if model in names:
                line(ok, "Gemini key works; model %s is available" % model)
            else:
                line(warn, "Gemini key works, but model %s is not available to it; set ISSUE_SCOUT_MODEL" % model)
        except ImportError:
            line(warn, "GOOGLE_API_KEY set, but google-genai is not installed")
        except Exception as exc:  # invalid key, network, ...
            line(fail, "Gemini key check failed: %s" % _short_error(exc))
            failed = True

    print("\nResult: %s" % ("problems found, see [FAIL] lines" if failed else "ready to use"))
    return 1 if failed else 0


def _short_error(exc: Exception) -> str:
    code, message = getattr(exc, "code", None), getattr(exc, "message", None)
    if code and message:
        return "%s: %s" % (code, message)
    return str(exc).splitlines()[0][:200]


def _emit(args, data, render) -> None:
    # Issue text can contain leaked credentials; never echo them.
    if args.json:
        print(redact_secrets(json.dumps(data, indent=2, default=str)))
    else:
        sys.stdout.write(redact_secrets(render()))


if __name__ == "__main__":
    sys.exit(main())
