"""One-shot terminal CLI: match a resume against one or more job descriptions.

Run from agents/resume-jd-match-agent/ with the virtual environment active:
    python scripts/match.py --resume samples/sample_resume.txt --jd samples/sample_jd.txt
    python scripts/match.py --resume ~/cv.pdf --jd samples/sample_jd_frontend.txt --pdf report.pdf
    python scripts/match.py --resume ~/cv.docx --jd a.txt --jd b.txt --jd c.txt      # rank 3 JDs
    python scripts/match.py --resume ~/cv.pdf --jd jd.txt --cover-letter

--resume and --jd accept a .pdf/.docx/.txt/.md path or the text itself.
Requests: ranking is free (local), a report is 1 (0 if cached), a cover letter +1.
"""

import argparse
import asyncio
import os
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv  # noqa: E402  (installed with google-adk)

load_dotenv(os.path.join(ROOT, "resume_jd_agent", ".env"))

from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

from resume_jd_agent import cache  # noqa: E402
from resume_jd_agent.agent import root_agent  # noqa: E402
from resume_jd_agent.documents import markdown_to_pdf  # noqa: E402
from resume_jd_agent.guardrails import DOWNLOAD_PREFIX  # noqa: E402
from resume_jd_agent.tools import rank_job_descriptions  # noqa: E402


class Session:
    """One ADK chat session, so a cover letter can follow the report."""

    def __init__(self):
        self.runner = InMemoryRunner(agent=root_agent, app_name="resume_jd_agent")
        self.session_id = None
        self.requests = 0

    async def send(self, text: str) -> str:
        if self.session_id is None:
            session = await self.runner.session_service.create_session(app_name="resume_jd_agent", user_id="cli")
            self.session_id = session.id
        reply = ""
        message = types.Content(role="user", parts=[types.Part(text=text)])
        async for event in self.runner.run_async(user_id="cli", session_id=self.session_id, new_message=message):
            if event.author == root_agent.name and event.usage_metadata:
                self.requests += 1  # only real Gemini responses carry usage metadata
            for call in event.get_function_calls() or []:
                print(f"tool call: {call.name}", file=sys.stderr)
            if event.error_message:
                raise RuntimeError(event.error_message)
            if event.is_final_response() and event.content and event.content.parts:
                text = "".join(p.text or "" for p in event.content.parts if not p.thought)
                # The "> Download:" event is for adk web; the CLI saves files with --out/--pdf.
                if not text.startswith(DOWNLOAD_PREFIX):
                    reply = text
        return reply.strip()


def print_ranking(resume: str, jds: list[str]) -> str:
    """Ranks JDs locally (0 requests) and returns the best JD's source."""
    result = rank_job_descriptions(resume, jds, SimpleNamespace(state={}))
    if result["status"] != "success":
        raise SystemExit(f"Error: {result['error_message']}")
    print("## JD Ranking (local keyword overlap, 0 requests)\n")
    print("| Rank | JD | Overlap | Top missing skills |\n| :--- | :--- | :--- | :--- |")
    for row in result["ranking"]:
        detail = row.get("error") or ", ".join(row["missing"][:5]) or "-"
        overlap = f"{row['overlap_percent']}%" if row["overlap_percent"] >= 0 else "unreadable"
        print(f"| {row['rank']} | {row['jd']} | {overlap} | {detail} |")
    print()
    return jds[result["ranking"][0]["index"] - 1]


def save(path: str, markdown: str, source_note: str) -> None:
    if path.lower().endswith(".pdf"):
        data = markdown_to_pdf(markdown)
        with open(path, "wb") as f:
            f.write(data)
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"<!-- {source_note} -->\n\n{markdown}\n")
    print(f"Saved to {path}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Match a resume against one or more job descriptions.")
    parser.add_argument("--resume", required=True, help=".pdf/.docx/.txt path, or the resume text")
    parser.add_argument("--jd", required=True, action="append", help="JD path or text; repeat to rank several")
    parser.add_argument("--out", help="save the report as Markdown (.md) or PDF (.pdf)")
    parser.add_argument("--pdf", help="save the report as PDF (same as --out file.pdf)")
    parser.add_argument("--rank-only", action="store_true", help="with several --jd: only rank, no Gemini call")
    parser.add_argument("--cover-letter", action="store_true", help="also write a cover letter (+1 request)")
    parser.add_argument("--no-cache", action="store_true", help="ignore the local report cache")
    args = parser.parse_args()

    if args.no_cache:
        os.environ[cache.CACHE_ENV] = "off"
    resume = os.path.expanduser(args.resume)
    jds = [os.path.expanduser(jd) for jd in args.jd]

    jd = jds[0]
    if len(jds) > 1:
        jd = print_ranking(resume, jds)
        if args.rank_only:
            return 0
        print(f"Full report for the best match: {os.path.basename(jd)}\n", file=sys.stderr)

    if not os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY") == "your-key-here":
        print("Error: set GOOGLE_API_KEY in resume_jd_agent/.env first (see README).", file=sys.stderr)
        return 1

    async def run() -> tuple[str, str]:
        report = await session.send(f"Resume: {resume}\nJob description: {jd}")
        letter = await session.send("Write a cover letter for this job.") if args.cover_letter else ""
        return report, letter

    session = Session()
    try:
        report, letter = asyncio.run(run())
    except RuntimeError as exc:
        print(f"Error from Gemini: {exc}", file=sys.stderr)
        return 1

    print(report)
    if letter:
        print("\n\n" + letter)
    print(f"\nGemini requests used: {session.requests}", file=sys.stderr)

    model_name = getattr(root_agent.model, "model", "Gemini")
    note = (
        f"Generated by scripts/match.py with {model_name} on "
        f"{os.path.basename(resume)} and {os.path.basename(jd)}."
    )
    for path in filter(None, [args.out, args.pdf]):
        save(path, report + (f"\n\n{letter}" if letter else ""), note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
