// Folds the event stream of one check into state the run view can render.

export const STAGES = [
  { id: "understand", name: "Understand", hint: "Read the README" },
  { id: "attempt", name: "Attempt", hint: "Run it as written" },
  { id: "investigate", name: "Investigate", hint: "Find the cause" },
  { id: "repair", name: "Repair", hint: "Propose a fix" },
  { id: "verify", name: "Verify", hint: "Rerun from scratch" },
  { id: "report", name: "Report", hint: "Write it up" },
];

const STATE_FROM_EVENT = { start: "active", done: "done", fail: "fail", skip: "skipped" };
const LOG_CAP = 4000;

export class RunModel {
  constructor() {
    this.stages = Object.fromEntries(STAGES.map((s) => [s.id, "pending"]));
    this.activeStage = null;
    this.runs = []; // one per sandbox run: as documented, after fix 1, ...
    this.preamble = []; // log lines before the first plan (image pulls etc.)
    this.toolCalls = [];
    this.diagnoses = [];
    this.diffs = [];
    this.notes = [];
    this.done = null;
    this.t = 0;
    this.round = 0;
    this.version = 0;
  }

  get current() {
    return this.runs[this.runs.length - 1] || null;
  }

  apply(ev) {
    const data = ev.data || {};
    this.t = Math.max(this.t, ev.t || 0);
    this.version += 1;
    switch (ev.kind) {
      case "stage": {
        const state = STATE_FROM_EVENT[data.state] || data.state;
        this.stages[data.stage] = state;
        if (state === "active") this.activeStage = data.stage;
        if (data.stage === "investigate" && state === "active") this.round += 1;
        if (data.stage === "verify" && state === "active" && this.current) this.current.isVerify = true;
        break;
      }
      case "plan":
        this.runs.push({
          label: data.label || (this.runs.length ? `after fix ${this.runs.length}` : "as documented"),
          plan: data.plan || { steps: [], skipped: [] },
          results: {},
          logs: [],
          currentStep: null,
          startedAt: ev.t,
        });
        break;
      case "step_start": {
        const run = this.ensureRun();
        run.results[data.index] = { status: "running", exit_code: null, startedAt: ev.t, duration: null };
        run.currentStep = data.index;
        run.logs.push({ kind: "prompt", step: data.index, text: data.command || "" });
        break;
      }
      case "step_end": {
        const run = this.ensureRun();
        const prev = run.results[data.index] || { startedAt: ev.t };
        run.results[data.index] = {
          ...prev,
          status: data.status,
          exit_code: data.exit_code,
          duration: Math.max(0, ev.t - (prev.startedAt ?? ev.t)),
        };
        run.logs.push({ kind: "end", step: data.index, status: data.status, exit_code: data.exit_code,
                        duration: run.results[data.index].duration });
        if (run.currentStep === data.index) run.currentStep = null;
        break;
      }
      case "log": {
        const line = { kind: "out", text: ev.message ?? "" };
        const run = this.current;
        if (!run) {
          this.preamble.push(line);
          break;
        }
        // the sandbox echoes "$ command" itself, the prompt line already shows it
        const step = run.currentStep;
        const cmd = step && run.plan.steps.find((s) => s.index === step);
        if (cmd && line.text.trim() === `$ ${cmd.command}`.trim()) break;
        line.step = step;
        run.logs.push(line);
        if (run.logs.length > LOG_CAP) run.logs.splice(0, run.logs.length - LOG_CAP);
        break;
      }
      case "tool_call":
        this.toolCalls.push({ round: this.round, tool: data.tool, args: data.args || {}, t: ev.t });
        break;
      case "diagnosis":
        this.diagnoses.push({ round: data.round, diagnosis: data.diagnosis || {} });
        break;
      case "diff":
        this.diffs.push({ round: data.round, diff: data.diff || "" });
        break;
      case "info":
      case "warn":
        this.notes.push({ kind: ev.kind, message: ev.message, t: ev.t });
        // sandbox notes such as "Creating a fresh virtual environment" belong in the terminal
        if (ev.kind === "info" && ev.message && !/^Report written to /.test(ev.message)) {
          const line = { kind: "sys", text: ev.message };
          if (this.current) this.current.logs.push(line);
          else this.preamble.push(line);
        }
        break;
      case "done":
        this.done = data;
        break;
      default:
        break;
    }
  }

  ensureRun() {
    if (!this.current) this.apply({ kind: "plan", t: this.t, data: { label: "as documented" } });
    return this.current;
  }

  stepCount(run = this.current) {
    return run ? run.plan.steps.length : 0;
  }

  failedStep(run) {
    if (!run) return null;
    for (const step of run.plan.steps) {
      const r = run.results[step.index];
      if (r && (r.status === "failed" || r.status === "timeout")) return { step, result: r };
    }
    return null;
  }
}

export const TOOL_TEXT = {
  read_file: (a) => {
    const range = a.start || a.end ? `, lines ${a.start || 1} to ${a.end || "end"}` : "";
    return { icon: "file-text", text: `Read ${a.path || "a file"}${range}` };
  },
  search: (a) => ({ icon: "magnifying-glass", text: `Searched the code for “${a.pattern || ""}”${a.path ? ` in ${a.path}` : ""}` }),
  list_files: (a) => ({ icon: "folder-open", text: `Listed files in ${a.path || "the project root"}` }),
};

export function describeTool(call) {
  const fn = TOOL_TEXT[call.tool];
  return fn ? fn(call.args || {}) : { icon: "terminal-window", text: `${call.tool} ${JSON.stringify(call.args || {})}` };
}
