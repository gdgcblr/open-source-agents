import assert from "node:assert/strict";
import { test } from "node:test";
import { assignIds, loadManifest } from "../src/collect.js";
import { findCandidates, tokenize } from "../src/similarity.js";

const fixture = new URL("../examples/colliding-tools.json", import.meta.url).pathname;

test("tokenize splits identifiers, drops stopwords and folds synonyms", () => {
  assert.deepEqual(tokenize("searchNotes"), ["search", "document"]);
  assert.deepEqual(tokenize("find_files"), ["search", "document"]);
  assert.deepEqual(tokenize("Use this tool to fetch the user's pages"), ["get", "person", "document"]);
});

test("the most similar cross-server pairs rank first", async () => {
  const tools = assignIds(await loadManifest(fixture));
  const pairs = findCandidates(tools);
  const top3 = pairs.slice(0, 3).map((p) => [p.a.id, p.b.id].sort().join(" ~ "));
  assert.deepEqual(top3.sort(), [
    "chat__send_message ~ mail__send_email",
    "drive__create_document ~ notes__create_note",
    "drive__search_files ~ notes__search_notes",
  ]);
  assert.ok(pairs[0]!.score > 0.8);
});

test("same-server pairs are skipped unless asked for", async () => {
  const tools = assignIds(await loadManifest(fixture));
  assert.ok(findCandidates(tools, { threshold: 0 }).every((p) => p.a.server !== p.b.server));
  assert.ok(findCandidates(tools, { threshold: 0, includeSameServer: true }).some((p) => p.a.server === p.b.server));
});

test("unrelated tools fall under the threshold", async () => {
  const tools = assignIds(await loadManifest(fixture));
  const pairs = findCandidates(tools);
  assert.ok(!pairs.some((p) => [p.a.name, p.b.name].includes("share_file") && [p.a.name, p.b.name].includes("send_message")));
});
