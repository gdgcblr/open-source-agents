import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { archiveStats, listSavedCases, loadSavedCase } from "../src/archive.mjs";
import { LAB_ROUTES } from "../src/lab-client.mjs";
import {
  _resetSessionsForTests,
  addIncidentNote,
  closeIncident,
  listIncidents,
  openSessionCount,
  startIncident,
  triageIntoIncident,
} from "../src/sessions.mjs";

test("model C: open in RAM, close archives to disk and leaves RAM", async () => {
  const dir = await mkdtemp(join(tmpdir(), "stacksentry-cases-"));
  process.env.STACKSENTRY_CASES_DIR = dir;
  _resetSessionsForTests();

  try {
    const opened = startIncident({ title: "Demo case" });
    assert.equal(openSessionCount(), 1);

    triageIntoIncident(opened.id, 'relation "users" does not exist SQLSTATE 42P01', {
      source: "test",
    });
    addIncidentNote(opened.id, "Checked migrations in staging");

    const closed = await closeIncident(opened.id);
    assert.equal(closed.storage, "disk");
    assert.ok(closed.archive.bytes > 0);
    assert.equal(openSessionCount(), 0);
    assert.equal(listIncidents().length, 0);

    const saved = await listSavedCases();
    assert.equal(saved.length, 1);
    assert.equal(saved[0].id, opened.id);

    const loaded = await loadSavedCase(opened.id);
    assert.equal(loaded.title, "Demo case");
    assert.equal(loaded.latest.category, "database-schema");
    assert.match(closed.reportMarkdown, /Checked migrations/);

    const stats = await archiveStats();
    assert.equal(stats.count, 1);
    assert.ok(stats.totalBytes > 100);
  } finally {
    _resetSessionsForTests();
    delete process.env.STACKSENTRY_CASES_DIR;
    await rm(dir, { recursive: true, force: true });
  }
});

test("lab route catalog is non-empty", () => {
  assert.ok(LAB_ROUTES.includes("/boom/schema"));
  assert.ok(LAB_ROUTES.includes("/boom/refused"));
});
