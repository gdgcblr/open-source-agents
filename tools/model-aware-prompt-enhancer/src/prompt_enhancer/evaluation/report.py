"""Human-readable benchmark reports (text or Markdown)."""

from __future__ import annotations

from typing import Any

from .runner import EvalReport


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def render_offline(rep: EvalReport, markdown: bool = False) -> str:
    s = rep.summary
    rows = [
        ("Cases", f"{s['cases']} ({s['passed']} passed, {s['failed']} failed)"),
        ("Requirement preservation (lock ok)", _pct(s["requirement_preservation_rate"])),
        ("Enhancement rate / no-change rate", f"{_pct(s['enhancement_rate'])} / {_pct(s['no_change_rate'])}"),
        ("Good prompts left unchanged", f"{_pct(s['good_prompts_left_unchanged_rate'])} of {s['good_prompts']}"),
        ("Expected-rule recall", _pct(s["expected_rule_recall"])),
        ("Unexpected rule firings", str(s["unexpected_rule_firings"])),
        ("Token overhead when changed (mean / max)", f"{s['token_overhead_mean_when_changed']} / {s['token_overhead_max']} ({rep.token_method})"),
        ("Time per prompt (mean / p95)", f"{s['ms_mean']} ms / {s['ms_p95']} ms"),
    ]
    if "regressions" in s:
        rows.append(("Regressions vs baseline", f"{s['regressions']} ({', '.join(rep.regressions) or 'none'}); fixed: {s['fixed_since_baseline']}"))
    out: list[str] = []
    title = "Offline benchmark (deterministic; measures the toolkit, not model answer quality)"
    if markdown:
        out += [f"### {title}", "", "| Metric | Value |", "| :-- | :-- |"] + [f"| {k} | {v} |" for k, v in rows]
        out += ["", "| Category | Cases | Passed | Enhanced | Lock ok |", "| :-- | --: | --: | --: | --: |"]
        out += [f"| {k} | {v['cases']} | {v['passed']} | {_pct(v['enhancement_rate'])} | {_pct(v['lock_ok_rate'])} |" for k, v in rep.by_category.items()]
        out += ["", "| Profile | Cases | Passed | Enhanced | Lock ok |", "| :-- | --: | --: | --: | --: |"]
        out += [f"| {k} | {v['cases']} | {v['passed']} | {_pct(v['enhancement_rate'])} | {_pct(v['lock_ok_rate'])} |" for k, v in rep.by_profile.items()]
    else:
        out.append(title)
        out += [f"  {k:<44} {v}" for k, v in rows]
        out.append("\n  by category:")
        out += [f"    {k:<12} {v['passed']}/{v['cases']} passed, enhanced {_pct(v['enhancement_rate'])}" for k, v in rep.by_category.items()]
        out.append("  by profile:")
        out += [f"    {k:<18} {v['passed']}/{v['cases']} passed, enhanced {_pct(v['enhancement_rate'])}" for k, v in rep.by_profile.items()]
    failed = [r for r in rep.results if not r.passed]
    if failed:
        out.append("\nFailures:" if not markdown else "\n**Failures**\n")
        for r in failed:
            out.append(f"  - {r.id}: " + "; ".join(r.failures))
    return "\n".join(out)


def render_e2e(d: dict[str, Any]) -> str:
    label = "MOCK provider: not a model measurement" if d["kind"] == "end-to-end-mock" else f"LLM end-to-end: {d['provider']} / {d['model']}"
    out = [
        f"End-to-end A/B ({label})",
        f"  trials per arm: {d['trials_per_arm']}; cases with checks: {d['cases_with_checks']}; compared: {d['compared']}; not enhanced: {d['not_enhanced']}",
        f"  wins / losses / ties: {d['wins']} / {d['losses']} / {d['ties']}",
        f"  check pass rate: original {_pct(d['original_check_pass_rate'])} -> enhanced {_pct(d['enhanced_check_pass_rate'])}",
        f"  note: {d['caveat']}",
        "",
    ]
    for g, v in d.get("by_group", {}).items():
        out.append(f"  group {g:<10} compared {v['compared']}: wins {v['wins']} / losses {v['losses']} / ties {v['ties']}; "
                   f"pass rate {_pct(v['original_check_pass_rate'])} -> {_pct(v['enhanced_check_pass_rate'])}")
    if d.get("by_group"):
        out.append("")
    for r in d["results"]:
        o, e = r["original"], r["enhanced"]
        out.append(f"  {r['id']:<28} {r['outcome']:<13} original {o['passed_checks']}/{o['total_checks']}  enhanced {e['passed_checks']}/{e['total_checks']}")
    return "\n".join(out)


# ----------------------------------------------------------------------------- comparison reports

_CSS = """
:root{--ground:#f5f7f9;--surface:#ffffff;--ink:#16202b;--muted:#5b6775;--line:#dce1e7;--accent:#1f6f8b;
--win:#1e7a46;--win-bg:#e6f4ec;--loss:#b42318;--loss-bg:#fdeceb;--tie:#5b6775;--tie-bg:#eef1f4;--add:#e6f4ec;--del:#fdeceb;}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--ground:#0f151b;--surface:#161e26;--ink:#e6ebf0;
--muted:#93a1af;--line:#26313c;--accent:#5bb4d1;--win:#4cc38a;--win-bg:#123323;--loss:#f0857a;--loss-bg:#3a1714;--tie:#93a1af;--tie-bg:#1d2630;--add:#123323;--del:#3a1714;}}
:root[data-theme="dark"]{color-scheme:dark;--ground:#0f151b;--surface:#161e26;--ink:#e6ebf0;--muted:#93a1af;--line:#26313c;--accent:#5bb4d1;
--win:#4cc38a;--win-bg:#123323;--loss:#f0857a;--loss-bg:#3a1714;--tie:#93a1af;--tie-bg:#1d2630;--add:#123323;--del:#3a1714;}
body{background:var(--ground);color:var(--ink);font:15px/1.55 "IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;}
.wrap{max-width:1080px;margin:0 auto;padding-inline:20px;padding-block:28px 56px;display:grid;gap:28px}
h1{font-size:28px;line-height:1.2;margin:0;text-wrap:balance;font-weight:600}
h2{font-size:18px;margin:0 0 12px;font-weight:600}
.meta{color:var(--muted);margin:6px 0 0;font-size:14px}
.mono,pre,code{font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace}
.lede{max-width:68ch;margin:10px 0 0}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:18px}
.tablewrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:middle;white-space:nowrap}
th{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:600}
.bar{display:flex;height:10px;border-radius:5px;overflow:hidden;min-width:140px;background:var(--tie-bg)}
.bar span{display:block;height:100%}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600;letter-spacing:.03em}
.win{background:var(--win-bg);color:var(--win)}.loss{background:var(--loss-bg);color:var(--loss)}.tie{background:var(--tie-bg);color:var(--tie)}
.tag{font-size:12px;color:var(--muted);border:1px solid var(--line);border-radius:6px;padding:1px 7px}
.cases{display:grid;gap:10px}
details.case{background:var(--surface);border:1px solid var(--line);border-radius:10px}
details.case>summary{list-style:none;cursor:pointer;display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center;padding:14px 16px}
details.case>summary::-webkit-details-marker{display:none}
details.case>summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:10px}
.cid{font-weight:600}
.score{margin-left:auto;color:var(--muted);font-variant-numeric:tabular-nums;font-size:14px}
.body{padding:0 16px 16px;display:grid;gap:14px}
.label{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:600;margin:0 0 6px}
pre{margin:0;white-space:pre-wrap;word-break:break-word;font-size:12.5px;line-height:1.5;background:var(--ground);border:1px solid var(--line);
border-radius:8px;padding:10px 12px;max-height:260px;overflow:auto}
pre .a{background:var(--add);display:block}pre .d{background:var(--del);display:block}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media (max-width:720px){.cols{grid-template-columns:1fr}}
.ans{display:grid;gap:8px}
.trial{border:1px solid var(--line);border-radius:8px;padding:10px}
.checks{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 8px}
.chk{font-size:12px;border-radius:6px;padding:1px 7px}
.chk.ok{background:var(--win-bg);color:var(--win)}.chk.bad{background:var(--loss-bg);color:var(--loss)}
.trial pre{max-height:200px;background:transparent;border:0;padding:0}
.note{color:var(--muted);font-size:14px;max-width:72ch}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""


def _e(s: Any) -> str:
    import html as _html
    return _html.escape(str(s), quote=True)


def _pct0(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def _diff_html(diff: str) -> str:
    lines = []
    for line in diff.splitlines():
        cls = "a" if line.startswith("+") and not line.startswith("+++") else "d" if line.startswith("-") and not line.startswith("---") else ""
        lines.append(f'<span class="{cls}">{_e(line)}</span>' if cls else _e(line))
    return "\n".join(lines)


def _arm_html(title: str, arm: dict[str, Any]) -> str:
    trials = []
    for i, a in enumerate(arm.get("answers", []), 1):
        chips = "".join(f'<span class="chk {"ok" if c["passed"] else "bad"}">{"✓" if c["passed"] else "✗"} {_e(c["name"])}</span>' for c in a["checks"])
        trials.append(f'<div class="trial"><div class="checks"><span class="tag">answer {i}</span>{chips}</div><pre>{_e(a["text"])}</pre></div>')
    head = f'{_e(title)} · {arm["passed_checks"]}/{arm["total_checks"]} checks passed'
    return f'<div><p class="label">{head}</p><div class="ans">{"".join(trials) or "<p class=note>No answers recorded.</p>"}</div></div>'


def render_e2e_html(d: dict[str, Any]) -> str:
    mock = d["kind"] == "end-to-end-mock"
    model = d.get("model", "")
    rows = []
    groups = d.get("by_group") or {"all": {k: d[k] for k in ("compared", "wins", "losses", "ties", "original_check_pass_rate", "enhanced_check_pass_rate")}}
    for g, v in groups.items():
        n = max(v["compared"], 1)
        bar = (f'<div class="bar" role="img" aria-label="{v["wins"]} wins, {v["losses"]} losses, {v["ties"]} ties">'
               f'<span style="width:{v["wins"] / n * 100:.1f}%;background:var(--win)"></span>'
               f'<span style="width:{v["losses"] / n * 100:.1f}%;background:var(--loss)"></span></div>')
        rows.append(f"<tr><td>{_e(g)}</td><td>{v['compared']}</td><td>{v['wins']} / {v['losses']} / {v['ties']}</td><td>{bar}</td>"
                    f"<td>{_pct0(v['original_check_pass_rate'])} → <strong>{_pct0(v['enhanced_check_pass_rate'])}</strong></td></tr>")
    cases = []
    for r in d["results"]:
        o, en = r["original"], r["enhanced"]
        outcome = r["outcome"]
        pill = {"win": "win", "loss": "loss"}.get(outcome, "tie")
        tags = "".join(f'<span class="tag">{_e(t)}</span>' for t in r.get("tags", []))
        applied = _e(", ".join(r.get("applied", [])) or "nothing")
        diff = f'<div><p class="label">What the tool changed ({applied})</p><pre>{_diff_html(r.get("diff", ""))}</pre></div>' if r.get("diff") else ""
        cases.append(
            f'<details class="case"><summary><span class="cid mono">{_e(r["id"])}</span>{tags}<span class="pill {pill}">{_e(outcome)}</span>'
            f'<span class="score">original {o["passed_checks"]}/{o["total_checks"]} · enhanced {en["passed_checks"]}/{en["total_checks"]}</span></summary>'
            f'<div class="body"><div><p class="label">Original prompt</p><pre>{_e(r.get("original_prompt", ""))}</pre></div>{diff}'
            f'<div class="cols">{_arm_html("Original prompt answers", o)}{_arm_html("Enhanced prompt answers", en)}</div></div></details>'
        )
    kind = "Mock provider: pipeline test only, not a model measurement." if mock else \
        f"Live answers from {_e(d['provider'])} / {_e(model)}, {d['trials_per_arm']} per prompt version, scored by the same automatic checks."
    return f"""<title>{_e(model)} prompt A/B</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;600&display=swap">
<style>{_CSS}</style>
<main class="wrap">
<header><h1>Original vs enhanced prompts on {_e(model)}</h1>
<p class="meta mono">{_e(d.get("run_at", ""))} · provider {_e(d["provider"])} · {d["cases_with_checks"]} cases · {d["trials_per_arm"]} answers per version</p>
<p class="lede">{kind} A case is a <span class="pill win">win</span> when the enhanced prompt's answers passed more checks than the original's,
a <span class="pill loss">loss</span> when fewer, and a <span class="pill tie">tie</span> when equal. Open any case to read the prompts and every answer.</p></header>
<section class="panel"><h2>Results by group</h2><div class="tablewrap"><table>
<thead><tr><th>Group</th><th>Cases</th><th>Win / loss / tie</th><th>Share</th><th>Checks passed</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>
<p class="note">answered: the tool asked a question and the case supplies the user's answer. restructured: the original already stated its requirements and the tool only added model-specific structure.</p></section>
<section><h2>Every case</h2><div class="cases">{"".join(cases)}</div></section>
<p class="note">{_e(d.get("caveat", ""))}</p>
</main>
"""


def render_e2e_markdown(d: dict[str, Any]) -> str:
    out = [f"### Prompt A/B: original vs enhanced on {d.get('model')} ({d['provider']}, {d['trials_per_arm']} answers per version)", "",
           "| Group | Cases | Win / loss / tie | Checks passed (original → enhanced) |", "| :-- | --: | :-- | :-- |"]
    for g, v in (d.get("by_group") or {}).items():
        out.append(f"| {g} | {v['compared']} | {v['wins']} / {v['losses']} / {v['ties']} | {_pct0(v['original_check_pass_rate'])} → {_pct0(v['enhanced_check_pass_rate'])} |")
    out += ["", "| Case | Group | Outcome | Original | Enhanced | Failed checks (original → enhanced) |", "| :-- | :-- | :-- | --: | --: | :-- |"]
    for r in d["results"]:
        o, en = r["original"], r["enhanced"]
        fo = ", ".join(sorted(set(o["failures"]))) or "none"
        fe = ", ".join(sorted(set(en["failures"]))) or "none"
        out.append(f"| `{r['id']}` | {', '.join(r.get('tags', []))} | {r['outcome']} | {o['passed_checks']}/{o['total_checks']} | "
                   f"{en['passed_checks']}/{en['total_checks']} | {fo} → {fe} |")
    out += ["", f"_{d.get('caveat', '')}_"]
    return "\n".join(out)
