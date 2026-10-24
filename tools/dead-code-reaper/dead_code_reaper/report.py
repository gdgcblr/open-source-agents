"""Outputs: the HTML report, the JSON report, the patch, and the terminal summary."""
from __future__ import annotations

import difflib
import html
import json
import shlex
from pathlib import Path

from .model import Removal, TestOnly

CONTEXT = 2
MAX_SNIPPET = 60


def build_patch(sources: dict[str, str], new_files: dict[str, str | None]) -> str:
    """A git-style unified diff, including deleted files."""
    chunks = []
    for rel in sorted(new_files):
        old = sources[rel]
        new = new_files[rel]
        a = old.splitlines(keepends=True)
        b = [] if new is None else new.splitlines(keepends=True)
        header = f"diff --git a/{rel} b/{rel}\n"
        if new is None:
            header += "deleted file mode 100644\n"
        diff = list(difflib.unified_diff(a, b, fromfile=f"a/{rel}",
                                         tofile="/dev/null" if new is None else f"b/{rel}"))
        if not diff:
            continue
        body = []
        for line in diff:
            if line.endswith("\n"):
                body.append(line)
            else:
                body.append(line + "\n\\ No newline at end of file\n")
        chunks.append(header + "".join(body))
    return "".join(chunks)


def _snippet(source: str, r: Removal) -> dict:
    lines = source.splitlines()
    if r.kind == "module":
        first, last = 1, min(len(lines), 25)
    else:
        first, last = max(1, r.start - CONTEXT), min(len(lines), r.end + CONTEXT)
    truncated = False
    if last - first + 1 > MAX_SNIPPET:
        last, truncated = first + MAX_SNIPPET - 1, True
    return {"first": first, "lines": lines[first - 1:last],
            "truncated": truncated or (r.kind == "module" and len(lines) > last)}


def report_data(*, project: str, root_arg: str, mode: str, readonly: bool, check_mode: str | None,
                runs: int, ai: str | None, removals: list[Removal], test_only: list[TestOnly],
                protected_count: int, files_scanned: int, sources: dict[str, str]) -> dict:
    numbered = [r for r in removals if r.number]
    by_key = {r.key: r for r in numbered}
    items = []
    for r in numbered:
        items.append({
            "number": r.number, "kind": r.kind, "name": r.name, "path": r.path,
            "start": r.start, "end": r.end, "lines": r.lines, "status": r.status,
            "status_reason": r.status_reason, "confidence": r.confidence, "reasons": r.reasons,
            "ai_note": r.ai_note, "risk": r.risk, "default_keep": r.default_keep,
            "used_by": [by_key[k].number for k in r.used_by if k in by_key],
            "held_by": by_key[r.held_by].number if r.held_by in by_key else None,
            "snippet": _snippet(sources.get(r.path, ""), r),
        })
    needed = [{"name": r.name, "kind": r.kind, "path": r.path, "start": r.start,
               "reason": r.status_reason} for r in removals if r.status == "needed"]
    return {
        "project": project, "mode": mode, "readonly": readonly, "check_mode": check_mode,
        "runs": runs, "ai": ai, "files_scanned": files_scanned, "protected": protected_count,
        "command": f"dead-code-reaper apply {shlex.quote(root_arg)}",
        "removals": items, "needed": needed,
        "test_only": [{"name": t.name, "kind": t.kind, "path": t.path, "start": t.start,
                       "used_in": t.used_in} for t in test_only],
    }


def write_html(path: Path, data: dict):
    payload = json.dumps(data).replace("</", "<\\/")
    title = html.escape(f"Dead code in {data['project']}")
    path.write_text(TEMPLATE.replace("__TITLE__", title).replace("__DATA__", payload),
                    encoding="utf-8")


def write_json(path: Path, data: dict):
    slim = {k: v for k, v in data.items()}
    slim["removals"] = [{k: v for k, v in r.items() if k != "snippet"} for r in data["removals"]]
    path.write_text(json.dumps(slim, indent=2), encoding="utf-8")


_NOUNS = {"class": ("class", "classes"), "unreachable": ("unreachable block", "unreachable blocks")}


def _plural(n: int, kind: str) -> str:
    one, many = _NOUNS.get(kind, (kind, kind + "s"))
    return f"{n} {one if n == 1 else many}"


def summary_lines(removals: list[Removal], test_only: list[TestOnly]) -> list[str]:
    numbered = [r for r in removals if r.number]
    ticked = [r for r in numbered if not r.default_keep]
    out = []
    counts: dict[str, int] = {}
    for r in numbered:
        counts[r.kind] = counts.get(r.kind, 0) + 1
    if numbered:
        kinds = ", ".join(_plural(n, k) for k, n in sorted(counts.items()))
        out.append(f"{_plural(len(numbered), 'removal')} ({kinds}), {sum(r.lines for r in numbered)} lines")
        if any(r.status != "candidate" for r in numbered):
            out.append(f"  ticked by default: {len(ticked)} ({sum(r.lines for r in ticked)} lines)")
    else:
        out.append("No dead code found.")
    needed = [r for r in removals if r.status == "needed"]
    if needed:
        out.append(f"  needed by the checks (not removable): {len(needed)}")
    if test_only:
        out.append(f"Test-only code: {len(test_only)}")
    return out


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#fafaf8;--panel:#fff;--side:#f3f2ee;--text:#1f1e1c;--muted:#6b6a65;--faint:#9a988f;
--border:#e3e1da;--dead:#fdecec;--deadline:#f3c4c4;--ok:#e6f4ea;--oktext:#1e6b34;--warn:#fdf3dc;
--warntext:#7a5200;--risk:#fde8e3;--risktext:#8a2c12;--accent:#2f5fb3;--code:#f6f5f1;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#181816;--panel:#201f1d;--side:#1c1b19;--text:#ecebe6;
--muted:#a6a49c;--faint:#7c7a72;--border:#34322e;--dead:#3a1f1f;--deadline:#5c2c2c;--ok:#183a24;
--oktext:#8fd6a5;--warn:#3d3016;--warntext:#f0c674;--risk:#40231a;--risktext:#f4a58a;--accent:#8fb1f0;
--code:#1b1a18;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:14px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{padding:16px 24px;border-bottom:1px solid var(--border);background:var(--panel)}
h1{font-size:18px;font-weight:600;margin:0 0 6px}
.stats{display:flex;flex-wrap:wrap;gap:6px 18px;color:var(--muted);font-size:13px}
.layout{display:grid;grid-template-columns:270px minmax(0,1fr);min-height:calc(100vh - 140px)}
nav{background:var(--side);border-right:1px solid var(--border);padding:12px 10px;position:sticky;top:0;
height:100vh;overflow:auto}
nav h2{font-size:12px;font-weight:600;color:var(--faint);margin:14px 6px 6px;text-transform:uppercase;
letter-spacing:.04em}
.dir{color:var(--muted);font-size:12px;padding:4px 6px 2px;overflow-wrap:anywhere}
.file{display:flex;justify-content:space-between;gap:8px;padding:3px 6px 3px 14px;border-radius:6px;
cursor:pointer;color:var(--text);text-decoration:none;font-size:13px}
.file:hover{background:var(--panel)}.file .n{color:var(--muted);font-variant-numeric:tabular-nums}
.side-item{padding:3px 6px;font-size:12px;color:var(--muted);overflow-wrap:anywhere}
main{padding:16px 24px 120px;min-width:0}
.fileblock{margin-bottom:28px}.fileblock>h3{font:600 13px ui-monospace,SFMono-Regular,Menlo,monospace;
margin:0 0 8px;color:var(--muted)}
.rm{border:1px solid var(--border);border-radius:10px;background:var(--panel);margin-bottom:12px;overflow:hidden}
.rm-head{display:flex;align-items:flex-start;gap:10px;padding:10px 12px}
.rm-head input{margin-top:3px;width:16px;height:16px;cursor:pointer}
.rm-title{font-weight:600;word-break:break-word}.num{color:var(--faint);font-weight:400;margin-right:4px}
.meta{color:var(--muted);font-size:12px}
.badge{display:inline-block;font-size:11px;padding:1px 7px;border-radius:999px;margin-left:6px;vertical-align:1px}
.b-ok{background:var(--ok);color:var(--oktext)}.b-warn{background:var(--warn);color:var(--warntext)}
.b-risk{background:var(--risk);color:var(--risktext)}
.note{font-size:13px;margin-top:3px}.risk{font-size:13px;margin-top:3px;color:var(--risktext)}
.why{font-size:12px;color:var(--faint);margin-top:2px}
.msg{font-size:12px;color:var(--risktext);margin-top:4px}
pre{margin:0;background:var(--code);border-top:1px solid var(--border);overflow-x:auto;
font:12px/1.6 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;padding:6px 0}
.ln{display:block;padding:0 12px;white-space:pre}.ln i{display:inline-block;width:42px;color:var(--faint);
font-style:normal;user-select:none}
.ln.dead{background:var(--dead);box-shadow:inset 3px 0 var(--deadline)}
.kept .ln.dead{background:transparent;box-shadow:none;color:var(--muted)}
.kept{opacity:.75}
.trunc{padding:0 12px;color:var(--faint);font-style:italic}
.list{border:1px solid var(--border);border-radius:10px;background:var(--panel);padding:6px 12px;margin-bottom:20px}
.list div{padding:4px 0;border-bottom:1px solid var(--border);font-size:13px}.list div:last-child{border:0}
code{font:12px ui-monospace,SFMono-Regular,Menlo,monospace}
.bar{position:fixed;left:0;right:0;bottom:0;background:var(--panel);border-top:1px solid var(--border);
padding:10px 24px;display:flex;flex-wrap:wrap;align-items:center;gap:10px 16px;
padding-bottom:calc(10px + env(safe-area-inset-bottom,0px))}
.bar code{background:var(--code);border:1px solid var(--border);border-radius:6px;padding:6px 10px;
flex:1;min-width:240px;overflow-x:auto;white-space:nowrap}
button{font:inherit;border:1px solid var(--border);background:var(--panel);color:var(--text);
border-radius:6px;padding:6px 12px;cursor:pointer}button:hover{border-color:var(--muted)}
.banner{background:var(--warn);color:var(--warntext);padding:8px 12px;border-radius:8px;margin-bottom:16px;font-size:13px}
@media (max-width:760px){.layout{grid-template-columns:1fr}nav{position:static;height:auto}}
</style>
</head>
<body>
<header><h1 id="title"></h1><div class="stats" id="stats"></div></header>
<div class="layout"><nav id="nav"></nav><main id="main"></main></div>
<div class="bar" id="bar"><span id="count"></span><code id="cmd"></code><button id="copy" type="button">Copy command</button></div>
<script type="application/json" id="data">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const R = D.removals, byNum = {}; R.forEach(r => byNum[r.number] = r);
const kept = new Set(R.filter(r => r.default_keep).map(r => r.number));
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const files = {}; R.forEach(r => (files[r.path] = files[r.path] || []).push(r));
const paths = Object.keys(files).sort();
const fid = p => 'f-' + p.replace(/[^A-Za-z0-9]/g, '_');

document.getElementById('title').textContent = 'Dead code in ' + D.project;
const stats = [D.files_scanned + ' files scanned', R.length + ' removals',
  R.reduce((a, r) => a + r.lines, 0) + ' lines', (D.mode === 'library' ? 'library' : 'application') + ' mode'];
if (!D.readonly) stats.push(D.check_mode === 'tests' ? 'proven against tests (' + D.runs + ' runs)' : 'no tests: compile and import check only');
stats.push(D.ai ? 'AI notes: ' + D.ai : 'AI notes off');
stats.push(D.protected + ' protected');
document.getElementById('stats').innerHTML = stats.map(s => '<span>' + esc(s) + '</span>').join('');

let nav = '<h2>Removals</h2>', lastDir = null;
paths.forEach(p => {
  const i = p.lastIndexOf('/'), dir = i >= 0 ? p.slice(0, i + 1) : './', base = p.slice(i + 1);
  if (dir !== lastDir) { nav += '<div class="dir">' + esc(dir) + '</div>'; lastDir = dir; }
  nav += '<a class="file" href="#' + fid(p) + '"><span>' + esc(base) + '</span><span class="n">' + files[p].length + '</span></a>';
});
if (!paths.length) nav += '<div class="side-item">None</div>';
if (D.test_only.length) nav += '<h2>Test-only</h2>' + D.test_only.map(t => '<div class="side-item">' + esc(t.path) + ' · ' + esc(t.name) + '</div>').join('');
if (D.needed.length) nav += '<h2>Needed by checks</h2>' + D.needed.map(t => '<div class="side-item">' + esc(t.path) + ' · ' + esc(t.name) + '</div>').join('');
document.getElementById('nav').innerHTML = nav;

function badges(r) {
  let b = '';
  if (r.status === 'verified') b += '<span class="badge b-ok">tests pass without it</span>';
  else if (r.status === 'unverified') b += '<span class="badge b-warn">unverified</span>';
  else if (r.status === 'candidate') b += '<span class="badge b-warn">not verified yet</span>';
  if (r.confidence < 50) b += '<span class="badge b-warn">low confidence</span>';
  if (r.risk) b += '<span class="badge b-risk">risk warning</span>';
  return b;
}
let html = '';
if (D.readonly) html += '<div class="banner">Read-only scan: nothing was run or verified. Use <code>dead-code-reaper run</code> to prove removals against your tests and choose what to delete.</div>';
paths.forEach(p => {
  html += '<section class="fileblock" id="' + fid(p) + '"><h3>' + esc(p) + '</h3>';
  files[p].forEach(r => {
    const s = r.snippet;
    let code = s.lines.map((l, k) => {
      const n = s.first + k, dead = n >= r.start && n <= r.end;
      return '<span class="ln' + (dead ? ' dead' : '') + '"><i>' + n + '</i>' + esc(l) + '</span>';
    }).join('');
    if (s.truncated) code += '<span class="trunc">… ' + (r.kind === 'module' ? 'whole file, ' + r.lines + ' lines' : 'truncated') + '</span>';
    html += '<div class="rm" id="rm-' + r.number + '"><div class="rm-head">' +
      (D.readonly ? '' : '<input type="checkbox" data-n="' + r.number + '" aria-label="Remove #' + r.number + '">') +
      '<div><div class="rm-title"><span class="num">#' + r.number + '</span>' + esc(r.name) + badges(r) + '</div>' +
      '<div class="meta">' + esc(r.kind) + ' · ' + r.lines + ' line' + (r.lines === 1 ? '' : 's') + ' · lines ' + r.start + '–' + r.end + ' · confidence ' + r.confidence + '</div>' +
      (r.ai_note ? '<div class="note">AI note: ' + esc(r.ai_note) + '</div>' : '') +
      (r.risk ? '<div class="risk">Risk warning: ' + esc(r.risk) + '</div>' : '') +
      '<div class="why">' + esc(r.reasons.join('; ')) + (r.status_reason ? ' · ' + esc(r.status_reason) : '') + '</div>' +
      '<div class="msg" id="msg-' + r.number + '">' + (r.held_by ? 'Starts kept because #' + r.held_by + ' starts kept.' : '') + '</div></div></div><pre>' + code + '</pre></div>';
  });
  html += '</section>';
});
if (D.test_only.length) {
  html += '<section class="fileblock"><h3>Test-only code (never removed)</h3><div class="list">' +
    D.test_only.map(t => '<div><code>' + esc(t.path) + ':' + t.start + '</code> ' + esc(t.name) + ' <span class="meta">used only by ' + esc(t.used_in.join(', ')) + '</span></div>').join('') + '</div></section>';
}
if (D.needed.length) {
  html += '<section class="fileblock"><h3>Needed by checks (found unused, but the checks fail without them)</h3><div class="list">' +
    D.needed.map(t => '<div><code>' + esc(t.path) + ':' + t.start + '</code> ' + esc(t.name) + ' <span class="meta">' + esc(t.reason) + '</span></div>').join('') + '</div></section>';
}
document.getElementById('main').innerHTML = html;

function compress(ns) {
  ns = [...ns].sort((a, b) => a - b); const out = [];
  for (let i = 0; i < ns.length;) { let j = i; while (j + 1 < ns.length && ns[j + 1] === ns[j] + 1) j++;
    out.push(i === j ? '' + ns[i] : ns[i] + '-' + ns[j]); i = j + 1; }
  return out.length ? out.join(',') : 'none';
}
function render() {
  R.forEach(r => {
    const box = document.querySelector('input[data-n="' + r.number + '"]');
    if (box) box.checked = !kept.has(r.number);
    document.getElementById('rm-' + r.number).classList.toggle('kept', kept.has(r.number));
  });
  const sel = R.filter(r => !kept.has(r.number));
  document.getElementById('count').textContent = sel.length + ' of ' + R.length + ' selected · ' + sel.reduce((a, r) => a + r.lines, 0) + ' lines';
  document.getElementById('cmd').textContent = D.command + ' --keep ' + compress(kept);
}
function keep(n, cause) {
  if (kept.has(n)) return; kept.add(n);
  if (cause) document.getElementById('msg-' + n).textContent = 'Kept because #' + cause + ' is kept.';
  R.forEach(r => { if (r.used_by.includes(n)) keep(r.number, n); });
}
if (D.readonly) { document.getElementById('bar').style.display = 'none'; }
else {
  document.getElementById('main').addEventListener('change', e => {
    const n = +e.target.dataset.n; if (!n) return;
    document.getElementById('msg-' + n).textContent = '';
    if (!e.target.checked) keep(n);
    else {
      const block = byNum[n].used_by.filter(m => kept.has(m));
      if (block.length) { document.getElementById('msg-' + n).textContent = 'Can’t remove: used by #' + block.join(', #') + ', which you’re keeping.'; }
      else kept.delete(n);
    }
    render();
  });
  document.getElementById('copy').addEventListener('click', () => {
    const t = document.getElementById('cmd').textContent, b = document.getElementById('copy');
    const done = () => { b.textContent = 'Copied'; setTimeout(() => b.textContent = 'Copy command', 1500); };
    if (navigator.clipboard) navigator.clipboard.writeText(t).then(done, () => {});
    else { const r = document.createRange(); r.selectNodeContents(document.getElementById('cmd'));
      const s = getSelection(); s.removeAllRanges(); s.addRange(r); document.execCommand('copy'); done(); }
  });
  render();
}
</script>
</body>
</html>
"""
