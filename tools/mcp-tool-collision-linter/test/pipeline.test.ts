import assert from "node:assert/strict";
import { test } from "node:test";
import { assignIds, loadManifest } from "../src/collect.js";
import { severity } from "../src/evaluate.js";
import { lint } from "../src/index.js";
import { extractJson, loadProbeFile, resolveToolRef } from "../src/probes.js";
import { OfflineProvider } from "../src/providers.js";
import { formatText, toJson, toMarkdown } from "../src/report.js";
import type { Provider, ToolChoiceRequest } from "../src/types.js";

const examples = new URL("../examples/", import.meta.url).pathname;

/**
 * A scripted "model": it routes every prompt to notes__search_notes or drive__search_files at random-ish,
 * unless the tool descriptions contain "Not for", which is what the rewrite step adds.
 */
class ScriptedModel implements Provider {
  readonly name = "scripted";
  calls = { choose: 0, complete: 0 };

  async chooseTool({ prompt, tools }: ToolChoiceRequest): Promise<string | null> {
    this.calls.choose++;
    const fixed = tools.some((t) => t.description.includes("Not for"));
    const wantsNotes = prompt.includes("[notes]");
    if (fixed) return wantsNotes ? "notes__search_notes" : "drive__search_files";
    return "drive__search_files"; // always picks drive: every notes probe is misrouted
  }

  async complete(system: string, user: string): Promise<string> {
    this.calls.complete++;
    if (system.includes("write test prompts")) {
      return "```json\n" + JSON.stringify({ a: ["[notes] a1", "[notes] a2"], b: ["[drive] b1", "[drive] b2"] }) + "\n```";
    }
    const ids = [...user.matchAll(/Tool id: (\S+)/g)].map((m) => m[1]!);
    return JSON.stringify({
      descriptions: Object.fromEntries(ids.map((id) => [id, `${id} rewritten. Not for the other kind of content.`])),
      rationale: "Separate by data source.",
    });
  }
}

test("probe → score → rewrite → re-test, end to end", async () => {
  const tools = await loadManifest(`${examples}colliding-tools.json`);
  const model = new ScriptedModel();
  const report = await lint(tools, model, { maxPairs: 1, probesPerTool: 2, verifyRewrites: true });

  assert.equal(report.evaluations.length, 1);
  const ev = report.evaluations[0]!;
  assert.deepEqual([ev.pair.a.id, ev.pair.b.id], ["notes__search_notes", "drive__search_files"]);
  assert.equal(ev.probes.length, 4);
  assert.equal(ev.aToB, 2);
  assert.equal(ev.bToA, 0);
  assert.equal(ev.confusionRate, 0.5);
  assert.equal(ev.severity, "high");
  assert.ok(ev.rewrite);
  assert.match(ev.rewrite.descriptions["notes__search_notes"]!, /Not for/);
  assert.deepEqual(ev.rewrite.after, { confusionRate: 0, accuracy: 1 });

  const text = formatText(report);
  assert.match(text, /notes\/search_notes {2}↔ {2}drive\/search_files/);
  assert.match(text, /Re-tested: confusion 50% → 0%/);
  assert.match(toMarkdown(report), /\| high \| 50% \|/);
  const parsed = JSON.parse(toJson(report));
  assert.equal(parsed.evaluations[0].pair.a.inputSchema, undefined, "JSON report omits schemas");
});

test("offline provider runs without any model and gives no rewrites", async () => {
  const tools = await loadManifest(`${examples}colliding-tools.json`);
  const report = await lint(tools, new OfflineProvider(), { maxPairs: 3 });
  assert.equal(report.evaluations.length, 3);
  assert.ok(report.evaluations.every((e) => e.rewrite === undefined));
  assert.ok(report.evaluations.every((e) => e.probes.length === 8));
});

test("static-only mode makes no model calls", async () => {
  const tools = await loadManifest(`${examples}colliding-tools.json`);
  const model = new ScriptedModel();
  const report = await lint(tools, model, { staticOnly: true });
  assert.equal(report.evaluations.length, 0);
  assert.ok(report.candidates.length > 0);
  assert.deepEqual(model.calls, { choose: 0, complete: 0 });
});

test("hand-written probes replace generated ones for the pairs they cover", async () => {
  const raw = await loadManifest(`${examples}colliding-tools.json`);
  const userProbes = await loadProbeFile(`${examples}probes.json`, assignIds(raw));
  const model = new ScriptedModel();
  const report = await lint(raw, model, { maxPairs: 1, userProbes, suggestRewrites: false });
  assert.equal(model.calls.complete, 0, "no probe generation when hand-written probes exist");
  assert.equal(report.evaluations[0]!.probes.length, 4);
});

test("tool refs resolve in every supported form", async () => {
  const tools = assignIds(await loadManifest(`${examples}colliding-tools.json`));
  for (const ref of ["notes/search_notes", "notes__search_notes", "search_notes"]) {
    assert.equal(resolveToolRef(ref, tools)?.id, "notes__search_notes");
  }
  assert.equal(resolveToolRef("nope/missing", tools), undefined);
});

test("extractJson tolerates fences and chatter", () => {
  assert.deepEqual(extractJson('Sure! ```json\n{"a": [1]}\n``` hope that helps'), { a: [1] });
  assert.deepEqual(extractJson('Here: {"b": 2} done'), { b: 2 });
  assert.throws(() => extractJson("no json here"));
});

test("severity thresholds", () => {
  assert.equal(severity(0.3, 0.7), "high");
  assert.equal(severity(0.1, 0.9), "medium");
  assert.equal(severity(0.05, 0.95), "low");
  assert.equal(severity(0, 0.5), "low");
  assert.equal(severity(0, 1), "none");
});
