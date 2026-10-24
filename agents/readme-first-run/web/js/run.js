// A check in progress (or a replay of a finished one).
import { getRun, listRuns, streamEvents } from "./api.js";
import { announce, clock, h, icon, put, reducedMotion, richText, shortPath } from "./dom.js";
import { RunModel, STAGES, describeTool } from "./model.js";
import {
  CATEGORY, VERDICT, diffView, engineName, evidenceList, ledger, parseDiff, skippedList, terminalLine,
} from "./components.js";
import { renderReport } from "./report.js";

const SPEEDS = [1, 4, 16];

export async function renderRun(main, ctx, id, { replay = false, speed = 1 } = {}) {
  let info = null;
  try {
    info = await getRun(id);
  } catch (err) {
    put(main, missingRun(id, err));
    return () => {};
  }
  if (info.state === "done" && info.report && !replay) {
    renderReport(main, id, info.report);
    return () => {};
  }
  return liveView(main, id, info, { replay, speed });
}

function missingRun(id, err) {
  return h("div", { class: "page narrow" },
    h("h1", { class: "display is-small" }, "This check is not here"),
    h("p", { class: "lede" }, err && err.status === 404
      ? `There is no run called ${id} in the runs folder. It may have been deleted.`
      : `FirstRun could not load ${id}: ${err ? err.message : "unknown error"}.`),
    h("p", null, h("a", { class: "btn", href: "#/history" }, icon("clock-counter-clockwise"), "Open history")));
}

function liveView(main, id, info, { replay, speed }) {
  const model = new RunModel();
  let disposed = false;
  let raf = 0;
  let follow = true;
  let tab = null; // index into model.runs, null = follow the latest
  let renderedTab = -1;
  let renderedLines = 0;
  let lastAnnounced = "";
  let wallStart = null;
  let speedNow = SPEEDS.includes(speed) ? speed : 1;
  let queue = [];
  let timer = 0;
  let replayClock = 0;
  let streamDone = false;

  const projectName = (info.report && info.report.project) || id.replace(/^\d{8}-\d{6}-/, "");

  // ---- skeleton
  const sourceEl = h("p", { class: "run-source" });
  const setSource = (src) => { sourceEl.textContent = shortPath(src); sourceEl.title = src || ""; };
  if (info.report) setSource(info.report.source);
  else listRuns().then((runs) => { const r = runs.find((x) => x.id === id); if (r) setSource(r.source); }).catch(() => {});
  const clockEl = h("span", { class: "run-clock-time" }, "00:00");
  const stateEl = h("span", { class: "run-clock-state" }, replay ? "Replay" : "Running");
  const rail = h("ol", { class: "rail", "aria-label": "Progress" });
  const ledgerTitle = h("h2", { class: "panel-title" }, "Steps from the README");
  const ledgerSlot = h("div", { class: "ledger-slot" },
    h("p", { class: "fine is-waiting" }, "Reading the README…"));
  const notesSlot = h("div", { class: "notes" });
  const nowLabel = h("span", { class: "now-label" }, "Now");
  const nowCmd = h("code", { class: "now-cmd" }, "Preparing a fresh sandbox");
  const nowMeta = h("span", { class: "now-meta" }, "");
  const nowBox = h("div", { class: "now", "aria-live": "off", "data-state": "running" }, nowLabel, nowCmd, nowMeta);
  const tabs = h("div", { class: "term-tabs", role: "group", "aria-label": "Show output of" });
  const term = h("div", { class: "term", role: "log", "aria-label": "Sandbox output", tabindex: "0" });
  const followBox = h("input", { type: "checkbox", checked: true, id: "follow" });
  const investigation = h("section", { class: "panel investigation", hidden: true, "aria-labelledby": "inv-title" });
  const correction = h("section", { class: "panel correction", hidden: true, "aria-labelledby": "fix-title" });

  followBox.addEventListener("change", () => {
    follow = followBox.checked;
    if (follow) term.scrollTop = term.scrollHeight;
  });
  term.addEventListener("scroll", () => {
    const atBottom = term.scrollHeight - term.scrollTop - term.clientHeight < 24;
    if (!atBottom && follow) { follow = false; followBox.checked = false; }
  }, { passive: true });

  const replayBar = replay ? h("div", { class: "replay-bar", role: "group", "aria-label": "Replay controls" },
    h("span", { class: "replay-label" }, icon("arrow-counter-clockwise"), "Replaying a recorded check"),
    h("div", { class: "segmented is-small" }, SPEEDS.map((s) => h("label", null,
      h("input", { type: "radio", name: "speed", value: String(s), checked: s === speedNow || null,
        onchange: () => {
          speedNow = s;
          // keep the speed in the URL so a reload or a shared link replays the same way
          history.replaceState(null, "", `#/run/${encodeURIComponent(id)}/replay${s === 1 ? "" : `?speed=${s}`}`);
        } }),
      h("span", null, `${s}x`)))),
    h("button", { type: "button", class: "btn is-quiet", onclick: () => flushReplay() }, "Skip to result"))
    : null;

  put(main, h("div", { class: "page run" },
    h("header", { class: "run-head" },
      h("div", { class: "run-title" },
        h("p", { class: "run-kicker" }, replay ? "Replay" : "Checking"),
        h("h1", { class: "run-name" }, projectName),
        sourceEl),
      h("div", { class: "run-clock", "aria-live": "off" }, stateEl, clockEl)),
    replayBar,
    rail,
    h("div", { class: "run-grid" },
      h("div", { class: "col-left" },
        h("section", { class: "panel col-ledger", "aria-labelledby": "ledger-title" },
          Object.assign(ledgerTitle, { id: "ledger-title" }), ledgerSlot, notesSlot),
        investigation,
        correction),
      h("section", { class: "panel col-term", "aria-label": "Terminal" },
        nowBox,
        tabs, term,
        h("label", { class: "follow" }, followBox, "Follow output")))));

  // ---- rendering

  function schedule() {
    if (!raf && !disposed) raf = requestAnimationFrame(() => { raf = 0; render(); });
  }

  function railDetail(stageId) {
    const st = model.stages[stageId];
    const doc = model.runs[0];
    const fix = model.runs.length > 1 ? model.current : null;
    const progress = (run) => {
      if (!run) return "";
      const n = run.plan.steps.length;
      const failed = model.failedStep(run);
      if (failed) return `failed at step ${failed.step.index}`;
      if (run.currentStep) return `step ${run.currentStep} of ${n}`;
      const doneCount = Object.values(run.results).filter((r) => r.status !== "running").length;
      return doneCount === n && n ? `all ${n} passed` : doneCount ? `${doneCount} of ${n} done` : "";
    };
    switch (stageId) {
      case "understand":
        if (!doc) return st === "active" ? "reading" : "";
        return `${doc.plan.steps.length} steps${(doc.plan.skipped || []).length ? `, ${doc.plan.skipped.length} skipped` : ""}`;
      case "attempt":
        return progress(doc);
      case "investigate": {
        const d = model.diagnoses[model.diagnoses.length - 1];
        if (d && st !== "active") return CATEGORY[d.diagnosis.category] || d.diagnosis.category;
        const calls = model.toolCalls.filter((c) => c.round === model.round).length;
        return st === "active" ? (calls ? `${calls} ${calls === 1 ? "lookup" : "lookups"}` : "looking") : "";
      }
      case "repair": {
        const last = model.diffs[model.diffs.length - 1];
        if (!last) return st === "active" ? "editing a copy" : "";
        const files = parseDiff(last.diff);
        const add = files.reduce((a, f) => a + f.add, 0);
        const del = files.reduce((a, f) => a + f.del, 0);
        return `+${add} -${del} in ${files.length === 1 ? files[0].path : `${files.length} files`}`;
      }
      case "verify":
        return progress(fix);
      case "report":
        return model.done ? (VERDICT[model.done.verdict] || {}).word || "" : "";
      default:
        return "";
    }
  }

  function renderRail() {
    put(rail, ...STAGES.map((s, i) => {
      let state = model.stages[s.id];
      if (model.done && state === "pending") state = "skipped";
      const label = { pending: "not started", active: "in progress", done: "done", fail: "failed", skipped: "not needed" }[state] || state;
      return h("li", { class: `rail-step is-${state}`, "aria-current": state === "active" ? "step" : null },
        h("span", { class: "rail-n", "aria-hidden": "true" },
          state === "done" ? icon("check") : state === "fail" ? icon("x") : String(i + 1)),
        h("span", { class: "rail-name" }, s.name, h("span", { class: "sr-only" }, `, ${label}`)),
        h("span", { class: "rail-detail" }, railDetail(s.id) || s.hint),
        h("span", { class: "rail-bar", "aria-hidden": "true" }));
    }));
  }

  function renderLedger() {
    const doc = model.runs[0];
    if (!doc) return;
    const fix = model.runs.length > 1 ? model.current : null;
    ledgerTitle.textContent = `Steps from ${doc.plan.readme_path || "the README"}`;
    put(ledgerSlot, 
      ledger({ docPlan: doc.plan, docResults: doc.results, fixPlan: fix && fix.plan, fixResults: fix ? fix.results : {},
               readmePath: doc.plan.readme_path, live: !model.done, compact: true }),
      skippedList(doc.plan.skipped));
    const warns = model.notes.filter((n) => n.kind === "warn");
    put(notesSlot, ...warns.map((n) => h("p", { class: "warn-note" }, icon("warning"), n.message)));
  }

  function setNow(state, label, text, meta) {
    nowBox.dataset.state = state;
    nowLabel.textContent = label;
    nowCmd.textContent = text;
    nowMeta.textContent = meta;
  }

  function renderNow() {
    const run = model.current;
    const step = run && run.currentStep && run.plan.steps.find((s) => s.index === run.currentStep);
    const failed = run && model.failedStep(run);
    const n = run ? run.plan.steps.length : 0;
    const where = (s) => `Step ${s.index} of ${n}${s.line ? `, README line ${s.line}` : ""}, ${run.label}`;
    if (step) {
      setNow("running", "Now running", step.command.replace(/\\\n\s*/g, " "), where(step));
    } else if (model.done) {
      const v = VERDICT[model.done.verdict] || {};
      setNow(v.state || "done", "Finished", v.word || "Finished", "Opening the report");
    } else if (model.activeStage === "investigate") {
      setNow("thinking", "Now", "Investigating the failure", model.round > 1 ? `Round ${model.round}` : "Reading the code around the error");
    } else if (model.activeStage === "repair") {
      setNow("thinking", "Now", "Applying the fix to a copy", "The original project is never touched");
    } else if (failed) {
      setNow("fail", `Failed ${run.label}`, failed.step.command.replace(/\\\n\s*/g, " "),
        `${where(failed.step)}. Kept as evidence before any fix.`);
    } else if (run && Object.keys(run.results).length && Object.values(run.results).every((r) => r.status !== "running")) {
      setNow("pass", "Passed", `All ${Object.keys(run.results).length} steps passed`, run.label);
    } else if (run && model.activeStage === "verify") {
      setNow("running", "Now", "Starting a second fresh sandbox", run.label);
    } else if (run) {
      setNow("running", "Now", "Starting a fresh sandbox", run.label);
    }
  }

  function renderTabs() {
    const active = tab ?? model.runs.length - 1;
    put(tabs, ...model.runs.map((r, i) => h("button", {
      type: "button", class: "term-tab", "aria-pressed": String(i === active),
      onclick: () => { tab = i === model.runs.length - 1 ? null : i; renderTerm(true); renderTabs(); },
    }, r.label.charAt(0).toUpperCase() + r.label.slice(1))));
    tabs.hidden = model.runs.length < 2;
  }

  function renderTerm(force = false) {
    const index = tab ?? model.runs.length - 1;
    const run = model.runs[index];
    if (!run) {
      if (force || renderedTab !== -2) {
        put(term, ...model.preamble.map((l) => terminalLine(l)));
        renderedTab = -2;
      }
      return;
    }
    if (force || renderedTab !== index) {
      put(term);
      renderedTab = index;
      renderedLines = 0;
    }
    const frag = document.createDocumentFragment();
    for (let i = renderedLines; i < run.logs.length; i++) frag.append(terminalLine(run.logs[i], run.plan));
    renderedLines = run.logs.length;
    term.append(frag);
    // keep the DOM bounded during long pip installs
    while (term.childElementCount > 1500) term.firstElementChild.remove();
    if (follow) term.scrollTop = term.scrollHeight;
  }

  const shown = new Set();
  function reveal(el) {
    if (shown.has(el)) return;
    shown.add(el);
    if (follow) requestAnimationFrame(() => el.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth", block: "nearest" }));
  }

  function renderInvestigation() {
    if (!model.toolCalls.length && !model.diagnoses.length && model.stages.investigate === "pending") return;
    investigation.hidden = false;
    reveal(investigation);
    const latest = model.diagnoses[model.diagnoses.length - 1];
    const d = latest && latest.diagnosis;
    const engine = d ? engineName(d.engine) : "";
    const calls = model.toolCalls;
    put(investigation, 
      h("div", { class: "panel-head" },
        h("h2", { class: "panel-title", id: "inv-title" }, "Investigation"),
        engine ? h("span", { class: "panel-meta" }, `by ${engine}`) : null),
      calls.length ? h("ol", { class: "lookups", "aria-label": "Files the investigator looked at" }, calls.map((c) => {
        const t = describeTool(c);
        return h("li", null, icon(t.icon), h("span", null, t.text));
      })) : (d ? null : h("p", { class: "fine is-waiting" }, "Matching the failure against known causes…")),
      d ? h("div", { class: "finding" },
        h("p", { class: "finding-kind" }, CATEGORY[d.category] || d.category,
          d.confidence ? h("span", { class: "finding-conf" }, `${d.confidence} confidence`) : null),
        h("p", { class: "finding-summary" }, richText(d.summary)),
        evidenceList(d.evidence),
        d.blocked && d.missing_env && d.missing_env.length
          ? h("p", { class: "warn-note is-blocked" }, icon("key"),
              `Needs ${d.missing_env.join(", ")}. FirstRun stops here rather than invent a value.`)
          : null)
        : null);
  }

  function renderCorrection() {
    const last = model.diffs[model.diffs.length - 1];
    if (!last) return;
    correction.hidden = false;
    reveal(correction);
    put(correction, 
      h("div", { class: "panel-head" },
        h("h2", { class: "panel-title", id: "fix-title" }, "Suggested correction"),
        h("span", { class: "panel-meta" }, model.stages.verify === "done" ? "verified from scratch"
          : model.stages.verify === "fail" ? "did not pass verification" : "applied to a copy, verifying")),
      diffView(last.diff));
  }

  function renderClock() {
    let t = model.t;
    if (!replay && !model.done && wallStart) t = Math.max(t, (Date.now() - wallStart) / 1000);
    if (replay) t = replayClock;
    clockEl.textContent = clock(t);
    if (model.done) stateEl.textContent = (VERDICT[model.done.verdict] || {}).word || "Finished";
  }

  function render() {
    renderRail();
    renderLedger();
    renderNow();
    renderTabs();
    renderTerm();
    renderInvestigation();
    renderCorrection();
    renderClock();
    const active = STAGES.find((s) => s.id === model.activeStage);
    const msg = model.done ? `Check finished: ${(VERDICT[model.done.verdict] || {}).word || model.done.verdict}`
      : active ? `${active.name}: ${railDetail(active.id) || "in progress"}` : "";
    if (msg && msg !== lastAnnounced && (model.done || !msg.includes("step "))) {
      lastAnnounced = msg;
      announce(msg);
    }
  }

  const tick = setInterval(() => !disposed && renderClock(), 500);

  // ---- events

  async function finish() {
    if (disposed) return;
    render();
    for (let attempt = 0; attempt < 20 && !disposed; attempt++) {
      try {
        const res = await getRun(id);
        if (res.report) {
          // a short beat so the room sees the last stamp land before the report replaces it
          await new Promise((r) => setTimeout(r, reducedMotion() ? 0 : 700));
          if (!disposed) renderReport(main, id, res.report, { reveal: true, replayed: replay });
          return;
        }
      } catch {
        /* report not written yet */
      }
      await new Promise((r) => setTimeout(r, 500));
    }
  }

  function onEvent(ev) {
    if (wallStart === null) wallStart = Date.now() - (ev.t || 0) * 1000;
    model.apply(ev);
    schedule();
    if (ev.kind === "done") finish();
  }

  function pump() {
    timer = 0;
    if (disposed) return;
    const step = 0.05 * speedNow; // replay seconds per 50ms tick
    replayClock += step;
    while (queue.length && queue[0].t <= replayClock) onEvent(queue.shift());
    // skip quiet stretches (pip downloads) so replays stay watchable
    if (queue.length && queue[0].t - replayClock > 2.5) replayClock = queue[0].t - 1.2;
    if (queue.length || !streamDone) timer = setTimeout(pump, 50);
  }

  function flushReplay() {
    clearTimeout(timer);
    while (queue.length) onEvent(queue.shift());
  }

  const stop = streamEvents(id, {
    onEvent: replay ? (ev) => { queue.push(ev); if (!timer) timer = setTimeout(pump, 50); } : onEvent,
    onEnd: () => { streamDone = true; },
    onError: (err) => {
      notesSlot.append(h("p", { class: "warn-note" }, icon("warning"), `${err.message} Reload the page to reconnect.`));
    },
  });

  render();

  return () => {
    disposed = true;
    stop();
    clearInterval(tick);
    clearTimeout(timer);
    cancelAnimationFrame(raf);
  };
}
