// Loads offlineCheck() straight from static/index.html, so the tests always run
// the exact code the browser runs (no copy that could drift).
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const HTML = path.join(__dirname, "..", "static", "index.html");

function loadOfflineCheck() {
  const html = fs.readFileSync(HTML, "utf8");
  const start = html.indexOf("const RULES=");
  const fnStart = html.indexOf("function offlineCheck(", start);
  const close = fnStart < 0 ? null : /\r?\n}\r?\n/.exec(html.slice(fnStart));
  if (start < 0 || !close) throw new Error("offline-rules block not found in index.html");
  const code = html.slice(start, fnStart + close.index + close[0].length);
  // t() translates flag keys in the page; here it returns the key itself.
  const sandbox = { t: (k) => k, URL };
  vm.runInNewContext(code + "\nthis.offlineCheck = offlineCheck;", sandbox);
  return sandbox.offlineCheck;
}

module.exports = { loadOfflineCheck };

// node tests/offline_rules.js eval/heldout.jsonl  -> accuracy of the browser checker
if (require.main === module) {
  const file = process.argv[2] || path.join(__dirname, "..", "eval", "dataset.jsonl");
  const check = loadOfflineCheck();
  const rows = fs.readFileSync(file, "utf8").split(/\r?\n/).filter((l) => l.trim()).map(JSON.parse);
  let tp = 0, fp = 0, tn = 0, fn = 0;
  for (const row of rows) {
    const verdict = check(row.text).verdict;
    const flagged = verdict !== "safe", isScam = row.label === "scam";
    if (flagged && isScam) tp++; else if (flagged) fp++; else if (isScam) fn++; else tn++;
    if (flagged !== isScam) console.log(`MISS  expected=${row.label.padEnd(5)} got=${verdict.padEnd(10)} ${row.text.slice(0, 70)}`);
  }
  console.log(`\nMode: offline (browser JS)   Dataset: ${path.basename(file)}   Messages: ${rows.length}`);
  console.log(`Accuracy:  ${(((tp + tn) / rows.length) * 100).toFixed(1)}%  (${tp + tn}/${rows.length})`);
  console.log(`Scams caught (recall):        ${tp}/${tp + fn}`);
  console.log(`Safe messages wrongly flagged: ${fp}/${fp + tn}`);
}
