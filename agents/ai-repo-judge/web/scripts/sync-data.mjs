// Copy the judge's output (../data) into public/data so Vite serves it; fall back to the bundled sample.
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const latest = join(root, "..", "data");
const sample = join(latest, "sample");
const src = existsSync(join(latest, "results.json")) ? latest : sample;
const dest = join(root, "public", "data");

if (!existsSync(join(src, "results.json"))) {
  console.warn("sync-data: no results.json found; run `judge run` first (the UI will show an empty state).");
  process.exit(0);
}
rmSync(dest, { recursive: true, force: true });
mkdirSync(dest, { recursive: true });
cpSync(join(src, "results.json"), join(dest, "results.json"));
cpSync(join(src, "pr"), join(dest, "pr"), { recursive: true });
console.log(`sync-data: ${src === latest ? "latest run" : "sample data"} → public/data`);
