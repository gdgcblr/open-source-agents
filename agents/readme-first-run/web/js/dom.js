// Tiny DOM helpers. Strings always go in as text nodes, never as HTML.

export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  // commands and file names should never be machine translated
  if (tag === "code") el.setAttribute("translate", "no");
  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (value === null || value === undefined || value === false) continue;
      if (key === "class") el.className = value;
      else if (key === "dataset") Object.assign(el.dataset, value);
      else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
      else if (key === "text") el.textContent = value;
      else if (value === true) el.setAttribute(key, "");
      else el.setAttribute(key, String(value));
    }
  }
  append(el, children);
  return el;
}

export function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

const SVG_NS = "http://www.w3.org/2000/svg";

export function icon(name, extraClass = "") {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", `icon ${extraClass}`.trim());
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);
  return svg;
}

// replaceChildren would turn null into the text "null", this skips empty slots
export function put(el, ...children) {
  el.replaceChildren();
  return append(el, children);
}

export function clear(el) {
  while (el.firstChild) el.firstChild.remove();
  return el;
}

export function seconds(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "";
  const s = Number(value);
  if (s < 10) return `${s.toFixed(1)} s`;
  if (s < 60) return `${Math.round(s)} s`;
  const m = Math.floor(s / 60);
  const rest = Math.round(s % 60);
  return rest ? `${m} min ${rest} s` : `${m} min`;
}

export function clock(value) {
  const s = Math.max(0, Math.floor(value || 0));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export function when(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h ago`;
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function oneLine(text, max = 90) {
  const flat = String(text || "").replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat;
}

// headlines from the server use `backticks` for commands, show those as code
export function richText(text) {
  return String(text || "").split("`").map((part, i) => (i % 2 ? h("code", null, part) : part)).filter((x) => x !== "");
}

// long absolute paths read badly in a header, keep the part people recognise
export function shortPath(text, max = 56) {
  const s = String(text || "");
  if (s.length <= max || s.includes("://")) return s;
  const parts = s.split("/").filter(Boolean);
  return `.../${parts.slice(-3).join("/")}`;
}

// Sandbox output is full of throwaway temp paths. On screen the work dir becomes ./ and the
// macOS framework interpreter becomes python; the raw log keeps every character.
const SANDBOX_PATHS = [
  [/(?:\/private)?\/[^\s"'():]*?\/firstrun-[\w-]+\/(?:work|patched\/[^\s"'/]+)\//g, "./"],
  [/(^|[\s"'(=])\/work\//g, "$1./"],
  [/\/Library\/Frameworks\/Python\.framework\/[^\s"':]*\/Python(?=[:\s])/g, "python"],
];

export function displayPath(text) {
  let out = String(text ?? "");
  for (const [re, rep] of SANDBOX_PATHS) out = out.replace(re, rep);
  return out;
}

export function tail(text, lines = 12) {
  const rows = String(text || "").replace(/\s+$/, "").split("\n");
  return rows.slice(-lines).join("\n");
}

let announcer;
export function announce(message) {
  announcer ||= document.getElementById("announcer");
  if (!announcer) return;
  announcer.textContent = "";
  // a fresh text node makes screen readers repeat identical messages too
  requestAnimationFrame(() => { announcer.textContent = message; });
}

let toastTimer;
export function toast(message) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = message;
  el.classList.add("is-visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("is-visible"), 2600);
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = h("textarea", { class: "sr-only", "aria-hidden": "true" });
    area.value = text;
    document.body.append(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  }
}

export const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
