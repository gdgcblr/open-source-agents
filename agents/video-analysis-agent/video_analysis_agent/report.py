"""Render the report to Markdown/JSON and the transcript to text files."""

from __future__ import annotations

from pathlib import Path

from .schemas import Report, Transcript, format_timestamp


def _ts(ts: str | None) -> str:
    return f"`[{ts}]` " if ts else ""


def _quote(q: str | None) -> str:
    return f"\n  > _{q}_" if q else ""


def transcript_text(transcript: Transcript) -> str:
    return "\n".join(
        f"[{format_timestamp(s.start)}]{' (low confidence)' if s.low_confidence else ''} {s.text}"
        for s in transcript.segments
    )


def render_markdown(report: Report) -> str:
    a, m = report.analysis, report.meta
    out = [f"# Video Analysis Report: {m.source}", ""]
    out.append(
        f"- **Duration:** {format_timestamp(m.duration)}  \n"
        f"- **Language:** {m.language or 'unknown'}  \n"
        f"- **Generated:** {m.generated_at}  \n"
        f"- **Models:** Whisper `{m.whisper_model or 'n/a'}`, LLM `{m.llm_provider}/{m.llm_model}`"
    )
    if m.audio_preprocessing:
        out.append(f"- **Audio preprocessing:** {', '.join(m.audio_preprocessing)}")
    out += ["", "## Summary", "", a.summary or "_No summary produced._", ""]

    def section(title: str, lines: list[str], empty: str, note: str = "") -> None:
        out.extend([f"## {title}", ""])
        if note:
            out.extend([f"_{note}_", ""])
        out.extend(lines if lines else [f"_{empty}_"])
        out.append("")

    section("Key points", [f"- {_ts(i.timestamp)}{i.point}{_quote(i.quote)}" for i in a.key_points], "None found.")
    section(
        "Decisions (confirmed)",
        [f"- {_ts(i.timestamp)}{i.decision}{_quote(i.quote)}" for i in a.decisions],
        "No confirmed decisions found in the transcript.",
        "Only items clearly agreed in the video.",
    )
    section(
        "Proposals & suggestions (not agreed)",
        [
            f"- {_ts(i.timestamp)}{i.suggestion}" + (f" _(proposed by {i.proposed_by})_" if i.proposed_by else "") + _quote(i.quote)
            for i in a.proposals
        ],
        "None found.",
        "Ideas that were floated but NOT confirmed.",
    )
    if a.action_items:
        rows = ["| Time | Task | Owner | Deadline |", "| --- | --- | --- | --- |"]
        for i in a.action_items:
            rows.append(f"| {i.timestamp or ''} | {i.task} | {i.owner or 'not stated'} | {i.deadline or 'not stated'} |")
        section("Action items", rows, "")
        out.extend(["_Evidence quotes:_", ""] + [f"- {_ts(i.timestamp)}_{i.quote}_" for i in a.action_items] + [""])
    else:
        section("Action items", [], "None found.")
    section(
        "Important facts",
        [f"- {_ts(i.timestamp)}**{i.kind}:** {i.value}" + (f" - {i.context}" if i.context else "") + _quote(i.quote) for i in a.facts],
        "None found.",
    )
    section("Unresolved questions & open discussion", [f"- {_ts(i.timestamp)}{i.question}{_quote(i.quote)}" for i in a.open_questions], "None found.")
    section(
        "AI-generated insights, conclusions & next steps",
        [f"- **{i.kind.replace('_', ' ')}:** {i.text}" + (f" ({_ts(i.timestamp).strip()})" if i.timestamp else "") for i in a.insights],
        "None.",
        "Inferred by the model; NOT statements from the video.",
    )

    low = sum(s.low_confidence for s in report.transcript.segments)
    notes = list(report.warnings)
    if low:
        notes.insert(0, f"{low} transcript segment(s) had low speech-recognition confidence; check them in transcript.txt.")
    if notes:
        section("Warnings", [f"- {n}" for n in notes], "")
    return "\n".join(out).rstrip() + "\n"


def write_outputs(report: Report, out_dir: Path, formats: str = "both") -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    (out_dir / "transcript.json").write_text(report.transcript.model_dump_json(indent=2), encoding="utf-8")
    (out_dir / "transcript.txt").write_text(transcript_text(report.transcript) + "\n", encoding="utf-8")
    written += [out_dir / "transcript.json", out_dir / "transcript.txt"]
    if formats in ("md", "both"):
        (out_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")
        written.append(out_dir / "report.md")
    if formats in ("json", "both"):
        (out_dir / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
        written.append(out_dir / "report.json")
    return written
