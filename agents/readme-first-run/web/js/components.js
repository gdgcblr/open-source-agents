// Building blocks shared by the live run, the report and the history list.
import { displayPath, h, icon, richText, seconds } from "./dom.js";

export const VERDICT = {
  passed: { word: "Works as documented", state: "pass", icon: "check-circle",
            line: "A newcomer can follow this README exactly as written." },
  fixed: { word: "Fixed and verified", state: "pass", icon: "check-circle",
           line: "Broken as documented. The suggested correction then passed from scratch in a fresh sandbox." },
  blocked: { word: "Blocked", state: "blocked", icon: "lock-simple",
             line: "Setup needs credentials FirstRun was not given, so it stopped instead of faking a result." },
  failed: { word: "Still broken", state: "fail", icon: "x-circle",
            line: "Broken as documented, and no correction passed verification." },
  error: { word: "Check did not finish", state: "fail", icon: "warning",
           line: "FirstRun could not complete this check." },
};

export const SHORT_VERDICT = { passed: "Passed", fixed: "Fixed", blocked: "Blocked", failed: "Broken", error: "Error" };

const STEP = {
  passed: { label: "Passed", state: "pass", icon: "check" },
  alive: { label: "Started", state: "pass", icon: "check" },
  failed: { label: "Failed", state: "fail", icon: "x" },
  timeout: { label: "Timed out", state: "fail", icon: "clock" },
  not_run: { label: "Not run", state: "muted", icon: null },
  running: { label: "Running", state: "active", icon: "spinner-gap" },
};

export function verdictTag(verdict) {
  const v = VERDICT[verdict];
  if (!v) return h("span", { class: "tag is-muted" }, "Running");
  return h("span", { class: `tag is-${v.state}` }, icon(v.icon), SHORT_VERDICT[verdict]);
}

export function stamp(result, { compact = false } = {}) {
  if (!result) return h("span", { class: `stamp is-empty${compact ? " is-compact" : ""}` }, h("span", { class: "sr-only" }, "Waiting"));
  const meta = STEP[result.status] || STEP.not_run;
  const code = result.exit_code !== null && result.exit_code !== undefined && result.exit_code !== 0
    ? ` ${result.exit_code}` : "";
  const extra = code ? h("span", { class: "stamp-code" }, compact ? code.trim() : `exit${code}`) : null;
  const title = [meta.label, code ? `exit${code}` : "", result.duration ? seconds(result.duration) : ""].filter(Boolean).join(", ");
  return h("span", { class: `stamp is-${meta.state}${compact ? " is-compact" : ""}`, title },
    meta.icon ? icon(meta.icon, meta.state === "active" ? "spin" : "") : null,
    h("span", { class: compact ? "sr-only" : "stamp-label" }, meta.label),
    extra);
}

function cmdText(command) {
  return String(command || "").replace(/\\\n\s*/g, " ").trim();
}

// Rows aligned by step position. When the fix changed a command, both versions are shown.
export function ledger({ docPlan, docResults, fixPlan, fixResults, readmePath, live = false, compact = false }) {
  const docSteps = (docPlan && docPlan.steps) || [];
  const fixSteps = (fixPlan && fixPlan.steps) || [];
  const hasFix = Boolean(fixPlan);
  const aligned = !hasFix || docSteps.length === fixSteps.length;
  const rows = [];
  const count = aligned ? Math.max(docSteps.length, fixSteps.length) : docSteps.length;

  for (let i = 0; i < count; i++) {
    const d = docSteps[i];
    const f = aligned ? fixSteps[i] : null;
    const step = d || f;
    const changed = d && f && cmdText(d.command) !== cmdText(f.command);
    const dRes = d ? docResults[d.index] : null;
    const fRes = f ? fixResults[f.index] : null;
    const isNow = live && ((dRes && dRes.status === "running") || (fRes && fRes.status === "running"));
    rows.push(h("li", { class: `ledger-row${isNow ? " is-now" : ""}${dRes && !fRes && (dRes.status === "failed" || dRes.status === "timeout") ? " is-failed" : ""}` },
      h("span", { class: "ledger-line", title: step.line ? `${readmePath || "README"} line ${step.line}` : "added by FirstRun" },
        step.provided_by_firstrun ? "+" : (step.line ? `L${step.line}` : "")),
      h("span", { class: "ledger-cmd" },
        changed ? h("del", { class: "cmd is-old" }, cmdText(d.command)) : null,
        h("code", { class: `cmd${changed ? " is-new" : ""}` }, cmdText(changed ? f.command : step.command)),
        step.long_running ? h("span", { class: "ledger-note" }, "Server, counts as passed while it stays up") : null,
        step.provided_by_firstrun ? h("span", { class: "ledger-note" }, "Prerequisite FirstRun installed") : null),
      h("span", { class: "ledger-res" }, d ? stamp(dRes, { compact }) : h("span", { class: "stamp is-empty" })),
      hasFix ? h("span", { class: "ledger-res" }, f ? stamp(fRes, { compact }) : h("span", { class: "stamp is-empty" })) : null,
    ));
  }

  const head = h("div", { class: `ledger-head${hasFix ? " has-fix" : ""}${compact ? " is-compact" : ""}`, "aria-hidden": "true" },
    h("span", null, "Line"), h("span", null, compact ? "Command" : "Command from the README"),
    h("span", null, compact ? "As written" : "As documented"), hasFix ? h("span", null, "After fix") : null);

  const list = h("ol", { class: `ledger${hasFix ? " has-fix" : ""}${compact ? " is-compact" : ""}`, "aria-label": "Steps from the README" }, rows);
  const parts = [head, list];
  if (hasFix && !aligned) {
    parts.push(h("p", { class: "fine" }, "The fix changed the number of steps, so the verification run is listed separately below."));
    parts.push(ledger({ docPlan: fixPlan, docResults: fixResults, readmePath, live, compact }));
  }
  return h("div", { class: "ledger-wrap" }, parts);
}

export function skippedList(skipped) {
  if (!skipped || !skipped.length) return null;
  return h("details", { class: "skipped" },
    h("summary", null, `${skipped.length} README ${skipped.length === 1 ? "line" : "lines"} not run`),
    h("ul", null, skipped.map((s) => h("li", null,
      h("code", { class: "cmd" }, cmdText(s.command)),
      h("span", { class: "skipped-why" }, s.line ? `Line ${s.line}: ${s.reason}` : s.reason)))));
}

// ---- diff

export function parseDiff(text) {
  const files = [];
  let file = null;
  let oldNo = 0;
  let newNo = 0;
  for (const raw of String(text || "").split("\n")) {
    if (raw.startsWith("diff --git ")) {
      const m = raw.match(/ b\/(.+)$/);
      file = { path: m ? m[1] : raw.slice(11), lines: [], add: 0, del: 0, isNew: false };
      files.push(file);
      continue;
    }
    if (!file) continue;
    if (raw.startsWith("new file mode")) { file.isNew = true; continue; }
    if (raw.startsWith("--- ") || raw.startsWith("+++ ") || raw.startsWith("index ")) continue;
    if (raw.startsWith("@@")) {
      const m = raw.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
      if (m) { oldNo = Number(m[1]); newNo = Number(m[2]); }
      file.lines.push({ kind: "hunk", text: raw });
      continue;
    }
    if (raw.startsWith("\\")) continue; // "\ No newline at end of file"
    if (raw.startsWith("+")) { file.lines.push({ kind: "add", text: raw.slice(1), no: newNo++ }); file.add++; }
    else if (raw.startsWith("-")) { file.lines.push({ kind: "del", text: raw.slice(1), no: oldNo++ }); file.del++; }
    else if (raw.length || file.lines.length) { file.lines.push({ kind: "ctx", text: raw.slice(1), no: newNo++ }); oldNo++; }
  }
  for (const f of files) {
    while (f.lines.length && f.lines[f.lines.length - 1].kind === "ctx" && !f.lines[f.lines.length - 1].text) f.lines.pop();
  }
  return files;
}

export function diffView(text, { compact = false } = {}) {
  const files = parseDiff(text);
  if (!files.length) return h("p", { class: "fine" }, "No file changes.");
  return h("div", { class: `diff${compact ? " is-compact" : ""}` }, files.map((f) =>
    h("figure", { class: "diff-file" },
      h("figcaption", { class: "diff-head" },
        h("code", { class: "diff-path" }, f.path),
        h("span", { class: "diff-stat" },
          f.isNew ? "new file, " : "",
          h("span", { class: "is-add" }, `+${f.add}`), " ", h("span", { class: "is-del" }, `-${f.del}`))),
      h("div", { class: "diff-body", role: "group", "aria-label": `Changes to ${f.path}` },
        // the first hunk header says nothing a reader needs, later ones mark a gap in the file
        f.lines.filter((l, i) => !(l.kind === "hunk" && (compact || i === 0))).map((l) =>
          h("div", { class: `dl is-${l.kind}` },
            h("span", { class: "dl-no", "aria-hidden": "true" }, l.kind === "hunk" ? "" : String(l.no)),
            h("span", { class: "dl-sign", "aria-hidden": "true" }, l.kind === "add" ? "+" : l.kind === "del" ? "-" : ""),
            h("span", { class: "dl-text" },
              l.kind === "add" ? h("span", { class: "sr-only" }, "Added: ") : null,
              l.kind === "del" ? h("span", { class: "sr-only" }, "Removed: ") : null,
              l.kind === "hunk" ? (l.text.replace(/^@@.*?@@\s?/, "") || "…") : (l.text || " "))))))));
}

// ---- terminal

const ERRORISH = /(Traceback|Error\b|ERROR|error:|No such file|not found|can't open|Errno|KeyError|exit status)/;

export function terminalLine(entry, plan) {
  if (entry.kind === "prompt") {
    const step = plan && plan.steps.find((s) => s.index === entry.step);
    return h("div", { class: "tl is-prompt" },
      h("span", { class: "tl-gutter" }, step && step.line ? `L${step.line}` : ""),
      h("span", { class: "tl-sign", "aria-hidden": "true" }, "$"),
      h("span", { class: "tl-text" }, entry.text));
  }
  if (entry.kind === "end") {
    const ok = entry.status === "passed" || entry.status === "alive";
    const text = entry.status === "alive"
      ? `still running after the watch window, counted as started (${seconds(entry.duration)})`
      : ok ? `done in ${seconds(entry.duration)}`
      : entry.status === "timeout" ? "timed out" : `exit ${entry.exit_code ?? "?"} after ${seconds(entry.duration)}`;
    return h("div", { class: `tl is-end ${ok ? "is-ok" : "is-bad"}` },
      h("span", { class: "tl-gutter" }), h("span", { class: "tl-sign", "aria-hidden": "true" }, ok ? "✓" : "✗"),
      h("span", { class: "tl-text" }, text));
  }
  if (entry.kind === "sys") {
    // FirstRun's own notes (fresh venv, image pull), not output of the project
    return h("div", { class: "tl is-sys" },
      h("span", { class: "tl-gutter" }), h("span", { class: "tl-sign", "aria-hidden": "true" }, "#"),
      h("span", { class: "tl-text" }, entry.text));
  }
  const raw = entry.text || "";
  const shown = displayPath(raw);
  const tone = /^\s*WARNING\b/.test(raw) ? " is-warn" : ERRORISH.test(raw) ? " is-err" : "";
  return h("div", { class: `tl${tone}`, title: shown !== raw ? raw : null },
    h("span", { class: "tl-gutter" }), h("span", { class: "tl-sign" }), h("span", { class: "tl-text" }, shown || " "));
}

export function outputBlock(text, { tone = "", lines = 14, label = "Output" } = {}) {
  const rows = String(text || "").replace(/\s+$/, "").split("\n");
  const cut = rows.length > lines;
  const shown = rows.slice(-lines);
  return h("div", { class: `term is-static ${tone}`, role: "group", "aria-label": label },
    cut ? h("div", { class: "tl is-more" }, h("span", { class: "tl-gutter" }), h("span", { class: "tl-sign" }),
      h("span", { class: "tl-text" }, `${rows.length - lines} earlier lines in the full log`)) : null,
    shown.map((t) => terminalLine({ kind: "out", text: t })));
}

export function evidenceList(evidence) {
  if (!evidence || !evidence.length) return null;
  return h("ul", { class: "evidence" }, evidence.map((e) => h("li", null,
    h("code", { class: "evidence-loc" }, e.line ? `${e.file}:${e.line}` : e.file),
    h("span", null, richText(e.note)))));
}

export const CATEGORY = {
  missing_dependency: "Missing dependency",
  undocumented_step: "Undocumented step",
  wrong_command: "Wrong command",
  missing_file: "Missing file",
  credentials_required: "Credentials required",
  template_leftover: "Template leftover",
  dependency_pin: "Dependency pin",
  interactive_input: "Needs typed input",
  platform_issue: "Platform issue",
  code_bug: "Bug in the code",
  unknown: "Unknown cause",
};

export function engineName(engine) {
  if (!engine) return "";
  if (engine.startsWith("gemini")) return "Gemini";
  if (engine.startsWith("groq")) return "Groq";
  return "Offline rules";
}
