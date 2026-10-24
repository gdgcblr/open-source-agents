// The "New check" screen.
import { getStatus, listRuns, startRun } from "./api.js";
import { h, icon, oneLine, put, richText, seconds, when } from "./dom.js";
import { STAGES } from "./model.js";
import { verdictTag } from "./components.js";

const PREFS_KEY = "firstrun.prefs";

function loadPrefs() {
  try {
    return JSON.parse(localStorage.getItem(PREFS_KEY) || "{}");
  } catch {
    return {};
  }
}

function savePrefs(prefs) {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs)); // never includes secrets
  } catch {
    /* private mode, fine */
  }
}

const HOW = {
  understand: "Reads the README and dependency files and lists the commands a newcomer would type.",
  attempt: "Runs them in order, in one shell, inside a sandbox that has never seen the project.",
  investigate: "Ties the first failure to its cause, with file and line evidence.",
  repair: "Proposes the smallest change to the README, requirements or .env.example.",
  verify: "Applies it to a copy and runs the whole setup again from scratch.",
  report: "Writes the report, the patch and a PR comment you can paste.",
};

export async function renderLaunch(main, ctx) {
  const prefs = { sandbox: "docker", offline: false, rounds: 2, image: "python:3.12-slim", ...loadPrefs() };
  // paint straight away from the status the top bar already fetched, refresh for next time
  let status = ctx.status;
  if (!status) {
    try {
      status = await getStatus();
      ctx.status = status;
    } catch {
      status = null;
    }
  } else {
    getStatus().then((s) => { ctx.status = s; }).catch(() => {});
  }
  const defaults = (status && status.defaults) || {};
  const gemini = Boolean(status && status.gemini && status.gemini.ok);
  const docker = status ? Boolean(status.docker && status.docker.ok) : true;
  if (!gemini) prefs.offline = true;
  if (!docker && prefs.sandbox === "docker") prefs.sandbox = "docker"; // keep the safe default, show the warning

  const target = h("input", {
    id: "target", name: "target", type: "text", class: "field-input is-large", required: true,
    autocomplete: "off", spellcheck: "false",
    "aria-describedby": "target-help target-error",
    placeholder: "examples/quote-of-the-day",
  });
  target.value = prefs.target || defaults.target || "examples/quote-of-the-day";
  const subdir = h("input", { id: "subdir", name: "subdir", type: "text", class: "field-input",
    autocomplete: "off", spellcheck: "false", "aria-describedby": "subdir-help" });
  const targetError = h("p", { id: "target-error", class: "field-error", role: "alert" });

  const radio = (name, value, checked, label, help, extra = {}) =>
    h("label", { class: `choice${extra.disabled ? " is-disabled" : ""}` },
      h("input", { type: "radio", name, value, checked: checked || null, disabled: extra.disabled || null }),
      h("span", { class: "choice-body" },
        h("span", { class: "choice-label" }, label),
        help ? h("span", { class: "choice-help" }, help) : null));

  const localWarning = h("p", { class: "warn-note", id: "local-warning", hidden: prefs.sandbox !== "local" || null },
    icon("warning"), "Local mode runs the README's commands on this computer, inside a temporary folder and venv. Use it only for projects you trust.");

  const imageInput = h("input", { id: "image", name: "image", type: "text", class: "field-input",
    autocomplete: "off", spellcheck: "false", value: prefs.image || defaults.image || "python:3.12-slim" });
  const secrets = h("textarea", { id: "secrets", name: "secrets", class: "field-input is-mono", rows: "3",
    autocomplete: "off", spellcheck: "false", "aria-describedby": "secrets-help", placeholder: "GEMINI_API_KEY=…" });

  const settings = h("details", { class: "settings", open: prefs.settingsOpen ? true : null },
    h("summary", null, icon("gear-six"), "Settings",
      h("span", { class: "settings-sum", id: "settings-sum" })),
    h("div", { class: "settings-grid" },
      h("fieldset", { class: "field" },
        h("legend", { class: "field-label" }, "Sandbox"),
        radio("sandbox", "docker", prefs.sandbox !== "local", "Docker container",
          docker ? "Isolated, removed after each run." : "Docker is not running. Start it, or use a local folder."),
        radio("sandbox", "local", prefs.sandbox === "local", "Local folder and fresh venv", "No Docker needed."),
        localWarning),
      h("fieldset", { class: "field" },
        h("legend", { class: "field-label" }, "Investigation"),
        radio("engine", "gemini", !prefs.offline && gemini, (status && status.gemini && status.gemini.label) || "Gemini",
          gemini ? `Reads files and searches the code (${status.gemini.model || "default model"}).`
                 : "Add GEMINI_API_KEY or GROQ_API_KEY to .env and restart to turn this on.", { disabled: !gemini }),
        radio("engine", "offline", prefs.offline || !gemini, "Offline rules", "Nothing leaves this machine.")),
      h("fieldset", { class: "field" },
        h("legend", { class: "field-label" }, "Repair attempts"),
        h("div", { class: "segmented" }, [0, 1, 2, 3].map((n) =>
          h("label", null,
            h("input", { type: "radio", name: "rounds", value: String(n), checked: Number(prefs.rounds) === n || null }),
            h("span", null, n === 0 ? "Report only" : String(n))))),
        h("p", { class: "field-help" }, "Each attempt is a full fresh install, so more attempts take longer.")),
      h("div", { class: "field" },
        h("label", { class: "field-label", for: "image" }, "Docker image"),
        imageInput,
        h("p", { class: "field-help" }, "Use python:3.12 when a project needs compilers or git.")),
      h("div", { class: "field is-wide" },
        h("label", { class: "field-label", for: "secrets" }, "Secrets for the checked project"),
        secrets,
        h("p", { class: "field-help", id: "secrets-help" },
          "One KEY=VALUE per line. Used for this check only, never saved, never written to a report."))));

  const runButton = h("button", { type: "submit", class: "btn is-primary is-large" }, icon("play"), "Run check");

  const form = h("form", { class: "launch-form", novalidate: true },
    h("div", { class: "field" },
      h("label", { class: "field-label", for: "target" }, "Project folder or GitHub URL"),
      h("div", { class: "target-row" }, target, runButton),
      h("p", { class: "field-help", id: "target-help" },
        "A path on this machine, or a link such as github.com/owner/repo/tree/main/agents/my-agent."),
      targetError),
    h("div", { class: "field is-inline" },
      h("label", { class: "field-label", for: "subdir" }, "Subfolder"),
      subdir,
      h("p", { class: "field-help", id: "subdir-help" }, "Optional. For one project inside a bigger repo.")),
    settings);

  const updateSummary = () => {
    const data = new FormData(form);
    const sb = data.get("sandbox") === "local" ? "local venv" : "Docker";
    const eng = data.get("engine") === "gemini" ? ((status && status.gemini && status.gemini.label) || "Gemini") : "offline rules";
    const r = Number(data.get("rounds"));
    form.querySelector("#settings-sum").textContent = `${sb}, ${eng}, ${r === 0 ? "report only" : `${r} repair ${r === 1 ? "attempt" : "attempts"}`}`;
    localWarning.hidden = data.get("sandbox") !== "local";
  };
  form.addEventListener("change", updateSummary);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    targetError.textContent = "";
    target.removeAttribute("aria-invalid");
    const value = target.value.trim();
    if (!value) {
      targetError.textContent = "Enter a project folder or a GitHub URL.";
      target.setAttribute("aria-invalid", "true");
      target.focus();
      return;
    }
    const data = new FormData(form);
    const rounds = Number(data.get("rounds"));
    const payload = {
      target: value,
      subdir: subdir.value.trim() || null,
      sandbox: data.get("sandbox") || "docker",
      image: imageInput.value.trim() || "python:3.12-slim",
      offline: data.get("engine") !== "gemini",
      max_rounds: Math.max(1, rounds),
      repair: rounds > 0,
      watch_seconds: defaults.watch_seconds || 20,
      secrets: secrets.value,
    };
    savePrefs({ target: value, sandbox: payload.sandbox, offline: payload.offline, rounds, image: payload.image,
                settingsOpen: settings.open });
    runButton.disabled = true;
    runButton.classList.add("is-busy");
    try {
      const res = await startRun(payload);
      secrets.value = "";
      location.hash = `#/run/${encodeURIComponent(res.id)}`;
    } catch (err) {
      runButton.disabled = false;
      runButton.classList.remove("is-busy");
      if (err.status === 409) {
        const running = err.body && err.body.active_run;
        targetError.append("Another check is still running. ",
          running ? h("a", { href: `#/run/${encodeURIComponent(running)}` }, "Watch it") : "Wait for it to finish.");
      } else {
        targetError.textContent = err.message || "FirstRun could not start this check.";
      }
      target.setAttribute("aria-invalid", "true");
      target.focus();
    }
  });

  // fixable samples first, they make the better first demo
  const order = { fixed: 0, failed: 1, blocked: 2, passed: 3 };
  const samples = [...((status && status.examples) || [])]
    .sort((a, b) => (order[a.expected_verdict] ?? 9) - (order[b.expected_verdict] ?? 9));
  const sampleList = samples.length ? h("section", { class: "samples", "aria-labelledby": "samples-title" },
    h("h2", { id: "samples-title", class: "section-title" }, "Try a broken sample"),
    h("p", { class: "section-lede" }, "Each one hides a mistake people make in real READMEs."),
    h("ul", { class: "sample-list" }, samples.map((s) => h("li", null,
      h("button", {
        type: "button", class: "sample", "aria-label": `Use ${s.name}: ${s.broken || s.summary || ""}`,
        onclick: () => {
          target.value = s.path;
          subdir.value = "";
          target.focus();
          target.select();
        },
      },
        h("span", { class: "sample-top" },
          h("code", { class: "sample-name" }, s.name),
          s.expected_verdict ? h("span", { class: "sample-expect" }, "Expect", verdictTag(s.expected_verdict)) : null),
        h("span", { class: "sample-what" }, richText(s.broken || s.summary || "")),
        h("span", { class: "sample-use", "aria-hidden": "true" }, "Use"))))))
    : null;

  const how = h("section", { class: "how", "aria-labelledby": "how-title" },
    h("h2", { id: "how-title", class: "section-title" }, "What a check does"),
    h("ol", { class: "how-list" }, STAGES.map((s, i) => h("li", null,
      h("span", { class: "how-n", "aria-hidden": "true" }, String(i + 1)),
      h("span", { class: "how-name" }, s.name),
      h("span", { class: "how-text" }, HOW[s.id])))));

  const latestSlot = h("div", { class: "latest-slot" });

  const busy = status && status.busy && status.active_run
    ? h("p", { class: "busy-note", role: "status" }, icon("spinner-gap", "spin"), "A check is running right now. ",
        h("a", { href: `#/run/${encodeURIComponent(status.active_run)}` }, "Watch it"))
    : null;

  put(main, 
    h("div", { class: "page launch" },
      h("div", { class: "launch-main" },
        busy,
        h("h1", { class: "display" }, "Run your README on a machine that has never seen it."),
        h("p", { class: "lede" },
          "FirstRun follows your setup steps in a fresh sandbox, keeps the first failure, and proves the fix."),
        form,
        sampleList),
      h("aside", { class: "launch-side" }, how, latestSlot)));
  updateSummary();

  try {
    const runs = await listRuns();
    const last = runs.find((r) => r.state === "done" && r.verdict);
    if (last) {
      const m = last.metrics || {};
      put(latestSlot, h("section", { class: "latest", "aria-labelledby": "latest-title" },
        h("h2", { id: "latest-title", class: "section-title" }, "Latest check"),
        h("a", { class: "latest-card", href: `#/run/${encodeURIComponent(last.id)}` },
          h("span", { class: "latest-top" }, h("code", { class: "latest-name" }, last.project), verdictTag(last.verdict)),
          h("span", { class: "latest-head" }, richText(oneLine(last.headline, 160))),
          h("span", { class: "latest-meta" },
            m.time_to_first_success != null ? `Time to first success ${seconds(m.time_to_first_success)}` : "No passing run",
            h("span", { class: "sep", "aria-hidden": "true" }), when(last.started_at)))));
    }
  } catch {
    /* history is optional on this screen */
  }
}
