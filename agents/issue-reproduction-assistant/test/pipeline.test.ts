import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, test } from "node:test";
import { getFileHistory } from "../src/git-history.js";
import { parseIssueRef } from "../src/github.js";
import { locate } from "../src/localize.js";
import { investigate } from "../src/pipeline.js";
import { parseReport } from "../src/report.js";
import { readRepositoryFiles } from "../src/repository-context.js";
import { describeMissingInformation, extractSignals } from "../src/signals.js";
import type { ModelProvider } from "../src/model-provider.js";

const dirs: string[] = [];
afterEach(async () => {
  await Promise.all(dirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
});

async function fixtureRepo(): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), "repro-pipeline-"));
  dirs.push(root);
  await mkdir(path.join(root, "src"));
  await mkdir(path.join(root, "test"));
  await writeFile(
    path.join(root, "src", "cache.ts"),
    "export function getCache(key: string) {\n  if (!store.has(key)) {\n    throw new Error('Cache entry missing for key');\n  }\n  return store.get(key);\n}\n",
  );
  await writeFile(path.join(root, "src", "other.ts"), "export const unrelated = 1;\n");
  await writeFile(path.join(root, "test", "cache.test.ts"), "import { getCache } from '../src/cache';\n");
  execFileSync("git", ["init", "-q"], { cwd: root });
  execFileSync("git", ["-c", "user.email=a@b.c", "-c", "user.name=T", "add", "."], { cwd: root });
  execFileSync("git", ["-c", "user.email=a@b.c", "-c", "user.name=T", "commit", "-qm", "add cache"], { cwd: root });
  return root;
}

const ISSUE = `# Cache throws after update

Steps to reproduce:
1. Call \`getCache\` after an update
2. Observe the error

Expected: value returned. Actual: crash on v1.4.2

Error: Cache entry missing for key
    at getCache (src/cache.ts:3:11)
`;

test("extracts stack frames, identifiers, errors and versions", () => {
  const signals = extractSignals(ISSUE);
  assert.ok(signals.stackFrames.some((f) => f.file === "src/cache.ts" && f.line === 3));
  assert.ok(signals.identifiers.includes("getCache"));
  assert.ok(signals.errorMessages.some((m) => m.includes("Cache entry missing")));
  assert.ok(signals.versions.includes("1.4.2"));
  assert.ok(signals.hasReproSteps);
  assert.ok(signals.hasExpectedActual);
});

test("parses python tracebacks and flags missing information", () => {
  const signals = extractSignals('Traceback:\n  File "app/db.py", line 42, in connect\nValueError: bad dsn');
  assert.ok(signals.stackFrames.some((f) => f.file === "app/db.py" && f.line === 42));
  const missing = describeMissingInformation(extractSignals("it is broken"));
  assert.ok(missing.length >= 4);
});

test("localizes the stack-trace file above unrelated files with line evidence", async () => {
  const root = await fixtureRepo();
  const files = await readRepositoryFiles(root);
  const ranked = locate(files, extractSignals(ISSUE));
  assert.equal(ranked[0].path, path.join("src", "cache.ts"));
  assert.ok(ranked[0].evidence.some((e) => e.line === 3));
  assert.ok(!ranked.some((c) => c.path.endsWith("other.ts")));
});

test("reads recent git history for a file and rejects path escapes", async () => {
  const root = await fixtureRepo();
  const history = await getFileHistory(root, "src/cache.ts");
  assert.equal(history[0].subject, "add cache");
  await assert.rejects(getFileHistory(root, "../../etc/passwd"), /escapes the repository/);
});

test("offline investigation needs no provider and reports evidence", async () => {
  const root = await fixtureRepo();
  const result = await investigate({ issueText: ISSUE, repositoryPath: root });
  assert.equal(result.mode, "offline");
  assert.equal(result.report.likelyAreas[0].path, path.join("src", "cache.ts"));
  assert.ok(result.existingTests.some((t) => t.endsWith("cache.test.ts")));
  assert.deepEqual(result.report.reproductionSteps, ["Call `getCache` after an update", "Observe the error"]);
});

test("LLM investigation validates JSON and drops hallucinated paths", async () => {
  const root = await fixtureRepo();
  let prompt = "";
  const provider: ModelProvider = {
    providerName: "mock",
    modelName: "m",
    async generateText(p, options) {
      prompt = p;
      assert.equal(options?.json, true);
      return "```json\n" + JSON.stringify({
        summary: "Cache lookup throws after update.",
        severity: "high",
        likelyAreas: [
          { path: path.join("src", "cache.ts"), reason: "throws", confidence: "high" },
          { path: "src/invented.ts", reason: "made up", confidence: "high" },
        ],
        reproductionTest: { suggestedPath: "test/repro.test.ts", framework: "node:test", code: "assert.fail()" },
      }) + "\n```";
    },
  };

  const result = await investigate({ issueText: ISSUE, repositoryPath: root, provider });
  assert.equal(result.mode, "llm");
  assert.equal(result.report.likelyAreas.length, 1);
  assert.match(result.warnings.join(" "), /Dropped 1/);
  assert.equal(result.report.reproductionTest?.framework, "node:test");
  assert.match(prompt, /untrusted data/);
});

test("falls back to offline evidence when the model output is unusable", async () => {
  const root = await fixtureRepo();
  const provider: ModelProvider = {
    providerName: "mock",
    modelName: "m",
    async generateText() {
      return "sorry, no JSON here";
    },
  };
  const result = await investigate({ issueText: ISSUE, repositoryPath: root, provider });
  assert.equal(result.mode, "offline");
  assert.match(result.warnings[0], /Model analysis failed/);
});

test("parseReport rejects missing summary", () => {
  assert.throws(() => parseReport('{"hypotheses": []}'), /missing a summary/);
});

test("parses GitHub issue references and rejects bad input", () => {
  assert.deepEqual(parseIssueRef("gdgcblr/open-source-agents#12"), { owner: "gdgcblr", repo: "open-source-agents", number: 12 });
  assert.deepEqual(parseIssueRef("https://github.com/a/b/issues/7#issuecomment-1"), { owner: "a", repo: "b", number: 7 });
  assert.throws(() => parseIssueRef("../../etc#1"), /Invalid GitHub issue reference/);
  assert.throws(() => parseIssueRef("a/b; rm -rf /#1"), /Invalid GitHub issue reference/);
});
