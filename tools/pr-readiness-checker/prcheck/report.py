"""Terminal and JSON rendering of a Report."""

from __future__ import annotations

from rich.console import Console
from rich.markup import escape

from .models import AIResult, Report, Severity, Status

_STATUS_STYLE = {
    Status.FAIL: ("FAIL", "bold red"),
    Status.WARN: ("WARN", "yellow"),
    Status.INFO: ("INFO", "cyan"),
    Status.PASS: ("PASS", "green"),
    Status.SKIP: ("SKIP", "dim"),
    Status.CRASH: ("BUG ", "bold magenta"),
}
_ORDER = [Status.CRASH, Status.FAIL, Status.WARN, Status.INFO, Status.SKIP, Status.PASS]
_SEVERITY_WORD = {Severity.ERROR: "error", Severity.WARN: "warning", Severity.INFO: "note"}


def to_json(report: Report) -> str:
    return report.model_dump_json(indent=2, exclude_none=False)


def render(report: Report, console: Console, *, verbose: bool = False) -> None:
    console.print(f"[bold]pr-readiness-checker[/bold] {report.tool_version} | {escape(report.target)}")
    context = [f"files: {report.file_mode}", f"template: {report.template_source}"]
    context.append(f"base: {report.base}" if report.base else "base: none")
    console.print(f"[dim]{' | '.join(context)}[/dim]\n")

    for status in _ORDER:
        results = [r for r in report.checks if r.status is status]
        if status is Status.PASS and not verbose:
            if results:
                console.print(f"[green]PASS[/green] {len(results)} check(s): {', '.join(r.id for r in results)}")
            continue
        for result in results:
            label, style = _STATUS_STYLE[status]
            console.print(f"[{style}]{label}[/{style}] [bold]{result.id}[/bold] {escape(result.title)}")
            if result.skip_reason:
                console.print(f"       [dim]{escape(result.skip_reason)}[/dim]")
            worst = max((f.severity.rank for f in result.findings), default=0)
            for f in result.findings:
                where = ""
                if f.file:
                    where = f" [dim]({escape(f.file)}{f':{f.line}' if f.line else ''})[/dim]"
                # When a check mixes severities, say which findings don't block.
                tag = f"[dim]({_SEVERITY_WORD[f.severity]})[/dim] " if f.severity.rank < worst else ""
                console.print(f"       - {tag}{escape(f.message)}{where}")

    if report.ai is not None:
        console.print()
        render_ai(report.ai, console)

    s = report.summary
    console.print()
    verdict = "[bold green]READY[/bold green]" if s.ready else "[bold red]NOT READY[/bold red]"
    strict = " (strict: warnings count)" if s.strict else ""
    console.print(f"Result: {verdict}{strict} | {s.errors} error(s), {s.warnings} warning(s), {s.infos} note(s)"
                  f" | {report.metrics.duration_ms} ms")
    if s.crashed:
        console.print("[bold magenta]A check crashed. This is a bug in prcheck, please report it.[/bold magenta]")


def render_ai(ai: AIResult, console: Console) -> None:
    title = f"[bold]AI README review[/bold] [dim]({ai.provider}/{ai.model}, advisory only)[/dim]"
    console.print(title)
    if ai.status != "ok" or ai.review is None:
        console.print(f"  [yellow]{ai.status}[/yellow]: {escape(ai.message or '')}")
    else:
        for c in ai.review.criteria:
            bar = "#" * c.score + "." * (5 - c.score)
            console.print(f"  {c.criterion:<22} {escape(f'[{bar}]')} {c.score}/5  [dim]{escape(c.reason)}[/dim]")
        if ai.review.top_fixes:
            console.print("  Top fixes:")
            for i, fix in enumerate(ai.review.top_fixes, start=1):
                console.print(f"    {i}. {escape(fix)}")
        console.print(f"  [dim]{escape(ai.review.summary)}[/dim]")
    for flag in ai.flags:
        console.print(f"  [yellow]guardrail:[/yellow] {escape(flag)}")
    for note in ai.notes:
        console.print(f"  [yellow]setup:[/yellow] {escape(note)}")
    if ai.redactions:
        console.print(f"  [yellow]guardrail:[/yellow] {ai.redactions} secret-like value(s) redacted before sending.")
    if ai.truncated:
        console.print("  [dim]README was truncated before sending.[/dim]")
    u = ai.usage
    if u.attempts:
        console.print(f"  [dim]tokens in/out: {u.prompt_tokens}/{u.output_tokens} | {u.latency_ms} ms | "
                      f"attempts: {u.attempts}[/dim]")
