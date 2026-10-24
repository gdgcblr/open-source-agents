// Runs the shared fixture tests/rule_cases.json against offlineCheck() taken
// from static/index.html. tests/test_rule_cases.py runs the same cases in Python.
//   node tests/test_offline_rules.js
"use strict";
const fs = require("fs");
const path = require("path");
const { loadOfflineCheck } = require("./offline_rules");

const ALLOWED = { safe: ["safe"], flagged: ["suspicious", "scam"], scam: ["scam"] };
const { cases } = JSON.parse(fs.readFileSync(path.join(__dirname, "rule_cases.json"), "utf8"));
const offlineCheck = loadOfflineCheck();

let failed = 0;
for (const c of cases) {
  const verdict = offlineCheck(c.text).verdict;
  if (!ALLOWED[c.expect].includes(verdict)) {
    failed++;
    console.log(`FAIL  [${c.gap}] expected ${c.expect}, got ${verdict}: ${c.text}`);
  }
}
console.log(`${cases.length - failed}/${cases.length} shared rule cases passed (browser offlineCheck)`);
process.exit(failed ? 1 : 0);
