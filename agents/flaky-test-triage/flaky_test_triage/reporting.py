"""Dashboard (self-contained HTML) and Slack / Teams message formatting."""
from __future__ import annotations

import html
from pathlib import Path

# verdict -> (label, color, slack emoji, unicode emoji)
VERDICTS = {
    "flaky": ("Flaky", "#f59e0b", ":large_orange_circle:", "\U0001F7E0"),
    "real_bug": ("Real bug", "#ef4444", ":red_circle:", "\U0001F534"),
    "environment_issue": ("Environment", "#3b82f6", ":large_blue_circle:", "\U0001F535"),
    "test_issue": ("Test issue", "#8b5cf6", ":large_purple_circle:", "\U0001F7E3"),
    "needs_investigation": ("Unclear", "#6b7280", ":white_circle:", "⚪"),
}
ORDER = list(VERDICTS)


def format_message(summary: dict, clusters: list[dict], fmt: str = "slack") -> str:
    """Build a short shareable message. fmt is "slack" or "teams"."""
    slack = fmt == "slack"
    bold = (lambda s: f"*{s}*") if slack else (lambda s: f"**{s}**")
    sep = "\n" if slack else "\n\n"
    bullet = "•" if slack else "-"
    total = summary["total"]

    counts = []
    for key in ORDER:
        n = summary["by_verdict"].get(key, 0)
        if n:
            label, _, se, ue = VERDICTS[key]
            counts.append(f"{se if slack else ue} {label}: {n}")

    lines = [bold(f"Flaky Test Triage: {total} failures analysed"), " | ".join(counts)]
    if clusters:
        lines.append(bold("Top root causes"))
        for i, c in enumerate(clusters[:3], 1):
            lines.append(f"{i}. {bold(str(c['percent']) + '% of failures')}: {c['root_cause']}")
        lines.append(bold("Next actions"))
        for c in clusters[:3]:
            lines.append(f"{bullet} {c['recommendation']}")
    if summary.get("skipped"):
        lines.append(f"_{summary['skipped']} file(s) skipped by guardrails_")
    lines.append("Full dashboard: reports/triage_dashboard.html")
    return sep.join(lines)


_CSS = """
:root{--bg:#f6f7fb;--card:#fff;--text:#1f2937;--muted:#6b7280;--line:#e5e7eb}
@media (prefers-color-scheme:dark){:root{--bg:#0f172a;--card:#1e293b;--text:#e2e8f0;--muted:#94a3b8;--line:#334155}}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--text)}
.wrap{max-width:1100px;margin:0 auto;padding:24px 16px}
h1{margin:0 0 4px;font-size:26px}.sub{color:var(--muted);margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px}
.card h2{margin:0 0 12px;font-size:16px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:16px}
.kpi{border-radius:12px;padding:14px;color:#fff}.kpi b{display:block;font-size:30px}
.donut{display:flex;gap:18px;align-items:center;flex-wrap:wrap}
.legend div{margin:4px 0}.dot{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:8px}
.bar{height:10px;border-radius:6px;background:var(--line);overflow:hidden;margin:6px 0 10px}.bar i{display:block;height:100%}
.pill{display:inline-block;padding:2px 10px;border-radius:999px;color:#fff;font-size:12px;font-weight:600}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:9px 8px;border-bottom:1px solid var(--line);font-size:14px;vertical-align:top}
th{color:var(--muted);font-weight:600}.muted{color:var(--muted)}
textarea{width:100%;min-height:170px;font:13px/1.4 ui-monospace,Menlo,monospace;background:var(--bg);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:10px}
"""


def _donut(summary: dict) -> str:
    total = max(summary["total"], 1)
    segs, offset = [], 25.0
    for key in ORDER:
        n = summary["by_verdict"].get(key, 0)
        if not n:
            continue
        pct = n * 100.0 / total
        segs.append(f'<circle r="15.9155" cx="21" cy="21" fill="none" stroke="{VERDICTS[key][1]}" '
                    f'stroke-width="6" stroke-dasharray="{pct:.2f} {100 - pct:.2f}" '
                    f'stroke-dashoffset="{offset:.2f}"/>')
        offset -= pct
    legend = "".join(
        f'<div><span class="dot" style="background:{VERDICTS[k][1]}"></span>'
        f'{VERDICTS[k][0]}: <b>{summary["by_verdict"][k]}</b></div>'
        for k in ORDER if summary["by_verdict"].get(k))
    return (f'<div class="donut"><svg width="160" height="160" viewBox="0 0 42 42">'
            f'<circle r="15.9155" cx="21" cy="21" fill="none" stroke="var(--line)" stroke-width="6"/>'
            f'{"".join(segs)}<text x="21" y="22.5" text-anchor="middle" font-size="7" '
            f'font-weight="700" fill="currentColor">{summary["total"]}</text></svg>'
            f'<div class="legend">{legend}</div></div>')


def render_dashboard(summary: dict, clusters: list[dict], results: list[dict], slack_text: str) -> str:
    """Return a self-contained HTML page. All dynamic text is HTML escaped."""
    e = html.escape
    kpis = "".join(
        f'<div class="kpi" style="background:{VERDICTS[k][1]}"><b>{summary["by_verdict"].get(k, 0)}</b>{VERDICTS[k][0]}</div>'
        for k in ORDER if summary["by_verdict"].get(k))

    cl = ""
    for c in clusters:
        color = VERDICTS.get(c["verdict"], VERDICTS["needs_investigation"])[1]
        plural = "test" if c["size"] == 1 else "tests"
        factor = f' <span class="muted">({e(c["factor"])})</span>' if c.get("factor") else ""
        cl += (f'<div><b>{e(c["id"])}</b> {c["size"]} {plural}, {c["percent"]}%{factor}'
               f'<div class="bar"><i style="width:{c["percent"]}%;background:{color}"></i></div>'
               f'<div>{e(c["root_cause"])}</div>'
               f'<div class="muted">Action: {e(c["recommendation"])}</div></div><hr style="border:0;border-top:1px solid var(--line)">')

    rows = ""
    for r in sorted(results, key=lambda x: (ORDER.index(x["verdict"]) if x["verdict"] in ORDER else 9, x["test"])):
        label, color, _, _ = VERDICTS.get(r["verdict"], VERDICTS["needs_investigation"])
        rows += (f'<tr><td>{e(r["test"])}<div class="muted">{e(r["file"])}</div></td>'
                 f'<td><span class="pill" style="background:{color}">{e(label)}</span></td>'
                 f'<td>{int(r["confidence"] * 100)}%</td><td>{e(r["category"])}</td>'
                 f'<td>{e(r["cluster"])}</td></tr>')

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Flaky Test Triage Dashboard</title>
<style>{_CSS}</style></head><body><div class="wrap">
<h1>Flaky Test Triage Dashboard</h1>
<div class="sub">{summary["total"]} failures analysed, {len(clusters)} root-cause clusters, {summary.get("skipped", 0)} skipped</div>
<div class="kpis">{kpis}</div>
<div class="grid"><div class="card"><h2>Failures by verdict</h2>{_donut(summary)}</div>
<div class="card"><h2>Root-cause clusters</h2>{cl}</div></div>
<div class="card" style="margin-top:16px"><h2>All failures</h2><table><thead><tr><th>Test</th><th>Verdict</th><th>Confidence</th><th>Category</th><th>Cluster</th></tr></thead><tbody>{rows}</tbody></table></div>
<div class="card" style="margin-top:16px"><h2>Slack message (copy and paste)</h2><textarea readonly>{e(slack_text)}</textarea></div>
</div></body></html>"""


def write_reports(out_dir: Path, summary: dict, clusters: list[dict], results: list[dict]) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    slack = format_message(summary, clusters, "slack")
    teams = format_message(summary, clusters, "teams")
    (out_dir / "triage_dashboard.html").write_text(render_dashboard(summary, clusters, results, slack), encoding="utf-8")
    (out_dir / "slack_report.txt").write_text(slack + "\n", encoding="utf-8")
    (out_dir / "teams_report.md").write_text(teams + "\n", encoding="utf-8")
    return {"dashboard": "reports/triage_dashboard.html", "slack": "reports/slack_report.txt",
            "teams": "reports/teams_report.md"}
