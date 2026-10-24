// Past checks, newest first.
import { listRuns } from "./api.js";
import { h, icon, oneLine, put, richText, seconds, when } from "./dom.js";
import { verdictTag } from "./components.js";

export async function renderHistory(main) {
  put(main, h("div", { class: "page history" },
    h("h1", { class: "display is-small" }, "History"),
    h("p", { class: "fine is-waiting" }, "Loading checks…")));

  let runs;
  try {
    runs = await listRuns();
  } catch (err) {
    main.querySelector(".is-waiting").textContent = `Could not load the history: ${err.message}`;
    return;
  }

  if (!runs.length) {
    put(main, h("div", { class: "page history" },
      h("h1", { class: "display is-small" }, "History"),
      h("div", { class: "empty" },
        h("p", { class: "lede" }, "No checks yet. Every check you run is kept here with its report, patch and full logs."),
        h("a", { class: "btn is-primary", href: "#/" }, icon("play"), "Run a check"))));
    return;
  }

  const rows = runs.map((r) => {
    const m = r.metrics || {};
    const href = `#/run/${encodeURIComponent(r.id)}`;
    return h("li", { class: "hrow" },
      h("a", { class: "hrow-main", href },
        h("span", { class: "hrow-top" }, h("code", { class: "hrow-name" }, r.project), verdictTag(r.verdict)),
        h("span", { class: "hrow-head" }, r.state === "running" ? "Running now" : richText(oneLine(r.headline, 170)))),
      h("span", { class: "hrow-ttfs" },
        m.time_to_first_success != null
          ? [h("span", { class: "hrow-k" }, "First success"), seconds(m.time_to_first_success)]
          : [h("span", { class: "hrow-k" }, "First success"), "not reached"]),
      h("span", { class: "hrow-when" }, when(r.started_at)),
      r.state === "done"
        ? h("a", { class: "btn is-quiet is-small", href: `${href}/replay`, "aria-label": `Replay the ${r.project} check` },
            icon("arrow-counter-clockwise"), "Replay")
        : h("a", { class: "btn is-quiet is-small", href }, "Watch"));
  });

  put(main, h("div", { class: "page history" },
    h("div", { class: "history-head" },
      h("h1", { class: "display is-small" }, "History"),
      h("p", { class: "fine" }, `${runs.length} ${runs.length === 1 ? "check" : "checks"} in the runs folder`)),
    h("ol", { class: "hlist" }, rows)));
}
