// The finished check: verdict, the before/fix/after story, and the evidence behind it.
import { fileUrl, getText } from "./api.js";
import { announce, copyText, h, icon, put, richText, seconds, shortPath, toast, when } from "./dom.js";
import {
  CATEGORY, VERDICT, diffView, engineName, evidenceList, ledger, outputBlock, skippedList,
} from "./components.js";

const BADGE = {
  passed: ["works as documented", "2f7d4f"],
  fixed: ["fix available", "a36a00"],
  blocked: ["needs credentials", "6b7686"],
  failed: ["setup broken", "b4322a"],
  error: ["check incomplete", "6b7686"],
};

function resultMap(run) {
  const map = {};
  for (const r of (run && run.results) || []) map[r.step.index] = r;
  return map;
}

function logName(label) {
  return `${String(label).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}.log`;
}

function failedOf(run) {
  return ((run && run.results) || []).find((r) => r.status === "failed" || r.status === "timeout") || null;
}

function lastOk(run) {
  const ok = ((run && run.results) || []).filter((r) => (r.status === "passed" || r.status === "alive") && r.output && r.output.trim());
  const runs = ok.filter((r) => r.step.kind === "run");
  return (runs.length ? runs : ok).slice(-1)[0] || null;
}

function cmd(step) {
  return String(step.command || "").replace(/\\\n\s*/g, " ").trim();
}

function badgeMarkdown(verdict) {
  const [msg, color] = BADGE[verdict] || BADGE.error;
  const enc = (s) => encodeURIComponent(s).replace(/-/g, "--");
  return `![FirstRun: ${msg}](https://img.shields.io/badge/${enc("FirstRun")}-${enc(msg)}-${color})`;
}

export function renderReport(main, id, report, { reveal = false, replayed = false } = {}) {
  const v = VERDICT[report.verdict] || VERDICT.error;
  const m = report.metrics || {};
  const doc = report.documented_run;
  const plan = report.documented_plan;
  const rounds = report.rounds || [];
  const verifiedRound = [...rounds].reverse().find((r) => r.verification);
  const fixRun = verifiedRound ? verifiedRound.verification : null;
  const fixPlan = verifiedRound ? verifiedRound.plan : null;
  const docFailed = failedOf(doc);
  const lastRound = rounds[rounds.length - 1];
  const diagnosis = lastRound ? lastRound.diagnosis : null;
  const s = report.settings || {};

  // ---- facts
  const facts = [];
  if (m.time_to_first_success != null) facts.push(["Time to first success", seconds(m.time_to_first_success)]);
  if (m.failed_at_step != null) {
    facts.push([report.verdict === "blocked" ? "Stopped at" : "Failed as documented at", `step ${m.failed_at_step} of ${m.steps_documented}`]);
  }
  else if (doc) facts.push(["Steps", `${m.steps_documented ?? doc.results.length}`]);
  if (m.fixes_applied) facts.push(["Changes in the fix", String(m.fixes_applied)]);
  if (m.sandbox_runs) facts.push(["Fresh sandboxes", String(m.sandbox_runs)]);
  if (m.total_seconds != null) facts.push(["Whole check", seconds(m.total_seconds)]);

  // ---- actions
  const copyComment = async () => {
    try {
      const text = await getText(id, "comment.md");
      toast((await copyText(text)) ? "PR comment copied" : "Copy failed, download report.md instead");
    } catch (err) {
      toast(err.message);
    }
  };
  const copyBadge = async () => {
    toast((await copyText(badgeMarkdown(report.verdict))) ? "Badge markdown copied" : "Copy failed");
  };
  const dl = (name, label, iconName = "download-simple") =>
    h("a", { class: "btn", href: fileUrl(id, name), download: name }, icon(iconName), label);

  const actions = h("div", { class: "actions" },
    h("button", { type: "button", class: "btn is-primary", onclick: copyComment }, icon("copy"), "Copy PR comment"),
    dl("report.md", "Report"),
    report.final_diff ? dl("fix.patch", "fix.patch", "git-diff") : null,
    report.verdict === "passed" || report.verdict === "fixed" ? dl("verified-setup.sh", "verified-setup.sh", "terminal-window") : null,
    h("button", { type: "button", class: "btn", onclick: copyBadge }, icon("copy"), "Copy badge"),
    h("a", { class: "btn is-quiet", href: `#/run/${encodeURIComponent(id)}/replay` }, icon("arrow-counter-clockwise"), replayed ? "Replay again" : "Replay"));

  const verdict = h("section", { class: `verdict is-${v.state}${reveal && !matchMedia("(prefers-reduced-motion: reduce)").matches ? " is-reveal" : ""}`,
    "aria-labelledby": "verdict-word" },
    h("p", { class: "verdict-project" }, h("code", null, report.project),
      h("span", { class: "verdict-source", title: report.source }, report.source !== report.project ? shortPath(report.source) : "")),
    h("h1", { class: "verdict-word", id: "verdict-word", tabindex: "-1" }, icon(v.icon), v.word),
    h("p", { class: "verdict-line" }, v.line),
    report.headline ? h("p", { class: "verdict-headline" }, richText(report.headline)) : null,
    // an error verdict already names the problem in its headline
    report.error && report.verdict !== "error" ? h("p", { class: "warn-note is-fail" }, icon("warning"), report.error) : null,
    facts.length ? h("dl", { class: "facts" }, facts.map(([k, val]) => h("div", null, h("dt", null, k), h("dd", null, val)))) : null,
    actions,
    h("p", { class: "verdict-meta" },
      [s.sandbox_detail || s.sandbox, s.engine ? `investigated with ${engineName(s.engine)}` : null, when(report.started_at)]
        .filter(Boolean).join(", ")));

  // ---- story
  const story = buildStory({ report, doc, plan, docFailed, fixRun, diagnosis, m });

  // ---- diagnosis rounds
  const why = rounds.length ? h("section", { class: "section why", "aria-labelledby": "why-title" },
    h("h2", { class: "section-title", id: "why-title" }, report.verdict === "blocked" ? "Why it stopped" : "Why it failed"),
    rounds.map((r) => {
      const d = r.diagnosis || {};
      return h("article", { class: "finding is-large" },
        rounds.length > 1 ? h("p", { class: "finding-round" }, `Round ${r.number}`) : null,
        h("p", { class: "finding-kind" }, CATEGORY[d.category] || d.category,
          h("span", { class: "finding-conf" }, `${d.confidence || "medium"} confidence, found by ${engineName(d.engine)}`)),
        h("p", { class: "finding-summary" }, richText(d.summary)),
        d.explanation && d.explanation.trim() ? h("p", { class: "finding-text" }, richText(d.explanation.trim())) : null,
        evidenceList(d.evidence),
        d.missing_env && d.missing_env.length ? h("p", { class: "warn-note is-blocked" }, icon("key"),
          `Missing: ${d.missing_env.join(", ")}. Paste it into Settings, Secrets for the checked project, or pass --env-file on the command line, then run the check again.`) : null,
        d.trace && d.trace.length ? h("details", { class: "trace" },
          h("summary", null, `Investigator looked at ${d.trace.length} ${d.trace.length === 1 ? "thing" : "things"}`),
          h("ol", null, d.trace.map((t) => h("li", null, h("code", null, t.tool), " ",
            h("span", null, Object.entries(t.args || {}).map(([k, val]) => `${k}=${val}`).join(", ")))))) : null);
    })) : null;

  // ---- steps
  const steps = doc ? h("section", { class: "section steps", "aria-labelledby": "steps-title" },
    h("h2", { class: "section-title", id: "steps-title" }, `Steps from ${(plan && plan.readme_path) || "the README"}`),
    ledger({ docPlan: plan, docResults: resultMap(doc), fixPlan, fixResults: resultMap(fixRun), readmePath: plan && plan.readme_path }),
    skippedList(plan && plan.skipped),
    h("p", { class: "fine logs" }, "Full logs: ",
      [doc, ...rounds.map((r) => r.verification).filter(Boolean)].map((run, i) => [
        i ? ", " : "",
        h("a", { href: fileUrl(id, `logs/${logName(run.label)}`), download: logName(run.label) }, run.label)]))) : null;

  // ---- output check
  const oc = report.output_check;
  const outputCheck = oc ? h("section", { class: "section output-check", "aria-labelledby": "oc-title" },
    h("h2", { class: "section-title", id: "oc-title" }, "Example output in the README"),
    h("p", { class: "section-lede" },
      oc.verdict === "matches" ? "What the README promises is what a newcomer sees." : "The README\u2019s example differs from what a fresh run prints.",
      " ", h("span", { class: "fine" }, `Similarity ${Number(oc.similarity || 0).toFixed(2)}${oc.note ? `, ${oc.note.charAt(0).toLowerCase()}${oc.note.slice(1)}` : ""}.`)),
    h("div", { class: "compare" },
      h("figure", null, h("figcaption", null, "Documented"), outputBlock(oc.documented, { lines: 30, label: "Documented output" })),
      h("figure", null, h("figcaption", null, "Actual, ", h("code", null, oc.command || "")),
        outputBlock(oc.actual, { lines: 30, label: "Actual output", tone: oc.verdict === "matches" ? "is-good" : "" })))) : null;

  // ---- hints
  const hints = report.static_hints && report.static_hints.length ? h("section", { class: "section hints", "aria-labelledby": "hints-title" },
    h("h2", { class: "section-title", id: "hints-title" }, "Also worth a look"),
    h("ul", { class: "hint-list" }, report.static_hints.map((t) => h("li", null, t)))) : null;

  put(main, h("div", { class: "page report" }, verdict, story, why, steps, outputCheck, hints));
  announce(`Check finished: ${v.word}`);
  if (reveal) main.querySelector("#verdict-word")?.focus?.();
}

function buildStory({ report, doc, plan, docFailed, fixRun, diagnosis, m }) {
  const n = plan ? plan.steps.length : 0;
  const cols = [];

  // as documented
  if (doc) {
    cols.push(h("article", { class: `story-col is-${docFailed ? "fail" : "pass"}` },
      h("h2", { class: "story-title" }, "As documented"),
      h("p", { class: "story-state" }, icon(docFailed ? "x-circle" : "check-circle"),
        docFailed ? `Failed at step ${docFailed.step.index} of ${n}` : `All ${n} steps passed`),
      docFailed ? h("p", { class: "story-cmd" },
        docFailed.step.line ? h("span", { class: "story-line" }, `README line ${docFailed.step.line}`) : null,
        h("code", null, `$ ${cmd(docFailed.step)}`)) : null,
      docFailed ? outputBlock(docFailed.output, { tone: "is-bad", lines: 9, label: "Output of the failing step" })
        : (lastOk(doc) ? outputBlock(lastOk(doc).output, { tone: "is-good", lines: 16, label: "Output" }) : null)));
  }

  if (report.verdict === "passed") {
    cols.push(h("article", { class: "story-col is-note" },
      h("h2", { class: "story-title" }, "Nothing to fix"),
      h("p", { class: "story-text" },
        `A sandbox that had never seen this project ran every documented step and finished in ${seconds(m.time_to_first_success)}.`),
      h("p", { class: "story-text" }, "verified-setup.sh holds the exact commands that passed, in order.")));
  } else if (report.verdict === "blocked") {
    const keys = (diagnosis && diagnosis.missing_env) || [];
    cols.push(h("article", { class: "story-col is-blocked" },
      h("h2", { class: "story-title" }, "What it needs"),
      h("p", { class: "story-state" }, icon("key"), keys.length ? keys.join(", ") : "An API key"),
      h("p", { class: "story-text" },
        "Everything before this step worked. FirstRun never invents credentials, so add the real value under Settings, Secrets and run the check again to test the rest.")));
  } else if (report.verdict === "error") {
    cols.push(h("article", { class: "story-col is-note" },
      h("h2", { class: "story-title" }, "What went wrong"),
      h("p", { class: "story-text" }, report.error ? "The check stopped before the README could be tested." : "The check stopped before it could reach a verdict."),
      h("p", { class: "story-text" }, "This says nothing about the README yet. Fix the problem named above and run the check again.")));
  } else if (report.final_diff) {
    cols.push(h("article", { class: "story-col is-fix" },
      h("h2", { class: "story-title" }, "Suggested correction"),
      h("p", { class: "story-state" }, icon("git-diff"), diagnosis ? (CATEGORY[diagnosis.category] || diagnosis.category) : "Edit"),
      diffView(report.final_diff, { compact: true })));
  } else if (diagnosis) {
    cols.push(h("article", { class: "story-col is-note" },
      h("h2", { class: "story-title" }, "No fix proposed"),
      h("p", { class: "story-text" }, diagnosis.summary)));
  }

  if (fixRun) {
    const failed = failedOf(fixRun);
    const ok = lastOk(fixRun);
    cols.push(h("article", { class: `story-col is-${failed ? "fail" : "pass"}` },
      h("h2", { class: "story-title" }, "After correction"),
      h("p", { class: "story-state" }, icon(failed ? "x-circle" : "check-circle"),
        failed ? `Still fails at step ${failed.step.index}` : `All ${fixRun.results.length} steps passed from scratch`),
      failed ? outputBlock(failed.output, { tone: "is-bad", lines: 9, label: "Output after the fix" })
        : ok ? h("p", { class: "story-cmd" }, h("code", null, `$ ${cmd(ok.step)}`)) : null,
      !failed && ok ? outputBlock(ok.output, { tone: "is-good", lines: 16, label: "Output after the fix" }) : null));
  }

  return h("section", { class: `story cols-${cols.length}`, "aria-label": "What happened" }, cols);
}
