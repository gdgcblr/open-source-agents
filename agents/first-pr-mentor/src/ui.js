// Tiny terminal formatting helpers (no dependencies). Respects NO_COLOR.
const on = !process.env.NO_COLOR && process.stdout.isTTY;
const wrap = (code) => (s) => (on ? `\x1b[${code}m${s}\x1b[0m` : String(s));

export const c = {
  bold: wrap(1), dim: wrap(2), green: wrap(32), yellow: wrap(33), red: wrap(31), cyan: wrap(36), magenta: wrap(35),
};

export const mark = (ok) => (ok === true ? c.green("✔") : ok === "warn" ? c.yellow("!") : c.red("✘"));

export function heading(text) {
  console.log(`\n${c.bold(c.cyan(text))}\n${c.dim("─".repeat(Math.min(70, text.length + 4)))}`);
}

export function verdictBadge(v) {
  return { good: c.green("GOOD PICK"), maybe: c.yellow("MAYBE"), risky: c.red("RISKY"), skip: c.red("SKIP") }[v] || v;
}
