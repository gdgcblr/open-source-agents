// Router, theme and the environment status in the top bar.
import { getStatus } from "./api.js";
import { h, icon, put } from "./dom.js";
import { renderLaunch } from "./launch.js";
import { renderRun } from "./run.js";
import { renderHistory } from "./history.js";

const main = document.getElementById("main");
const ctx = { status: null };
let dispose = null;

function parseHash() {
  const raw = location.hash.replace(/^#/, "") || "/";
  const [path, query = ""] = raw.split("?");
  const params = new URLSearchParams(query);
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  return { parts, params };
}

function setNav(name) {
  for (const a of document.querySelectorAll(".nav a")) {
    if (a.dataset.nav === name) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
}

let routeToken = 0;

async function route() {
  const token = ++routeToken;
  if (dispose) {
    dispose();
    dispose = null;
  }
  const { parts, params } = parseHash();
  window.scrollTo(0, 0);
  if (parts[0] === "run" && parts[1]) {
    setNav(null);
    document.title = `${parts[1].replace(/^\d{8}-\d{6}-/, "")} - FirstRun`;
    const replay = parts[2] === "replay";
    const stop = await renderRun(main, ctx, parts[1], { replay, speed: Number(params.get("speed")) || 1 });
    // the user may have navigated away while the run was loading
    if (token !== routeToken) stop();
    else dispose = stop;
  } else if (parts[0] === "history") {
    setNav("history");
    document.title = "History - FirstRun";
    await renderHistory(main);
  } else {
    setNav("new");
    document.title = "FirstRun";
    await renderLaunch(main, ctx);
  }
  main.focus({ preventScroll: true });
}

async function refreshEnv() {
  const slot = document.getElementById("env");
  try {
    const st = await getStatus();
    ctx.status = st;
    const docker = st.docker || {};
    const gemini = st.gemini || {};
    put(slot, 
      h("span", { class: `env-item is-${docker.ok ? "ok" : "off"}`, title: docker.detail || "" },
        icon("cube"), docker.ok ? "Docker ready" : "Docker off"),
      h("span", { class: `env-item is-${gemini.ok ? "ok" : "off"}`, title: gemini.model || "" },
        icon("key"), gemini.ok ? `${gemini.label || "Gemini"} on` : "Offline rules"));
  } catch {
    put(slot, h("span", { class: "env-item is-off" }, icon("warning"), "FirstRun server unreachable"));
  }
}

// ---- theme: auto (system), light or dark; only the choice is remembered
const THEMES = ["auto", "light", "dark"];
const THEME_ICON = { auto: "circle-half", light: "sun", dark: "moon" };

const THEME_NAME = { auto: "match the system", light: "light", dark: "dark" };

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  const next = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
  const btn = document.getElementById("theme");
  put(btn, icon(THEME_ICON[theme]));
  btn.setAttribute("aria-label", `Color theme: ${THEME_NAME[theme]}. Switch to ${THEME_NAME[next]}`);
  btn.title = `Theme: ${THEME_NAME[theme]}`;
  syncThemeColor();
}

// the browser chrome should match the page, including when "auto" follows the system
function syncThemeColor() {
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = getComputedStyle(document.body).getPropertyValue("--paper").trim() || "#edf0f4";
}
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", syncThemeColor);

function initTheme() {
  let theme = "auto";
  try {
    theme = localStorage.getItem("firstrun.theme") || "auto";
  } catch {
    /* ignore */
  }
  applyTheme(THEMES.includes(theme) ? theme : "auto");
  document.getElementById("theme").addEventListener("click", () => {
    const next = THEMES[(THEMES.indexOf(document.documentElement.dataset.theme) + 1) % THEMES.length];
    applyTheme(next);
    try {
      localStorage.setItem("firstrun.theme", next);
    } catch {
      /* ignore */
    }
  });
}

initTheme();
refreshEnv();
setInterval(refreshEnv, 30000);
window.addEventListener("hashchange", route);
route();
