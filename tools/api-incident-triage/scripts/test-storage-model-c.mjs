/**
 * End-to-end demo of storage model C:
 *   open = RAM · close = disk archive · next incident = fresh RAM
 *
 * Run: node scripts/test-storage-model-c.mjs
 */
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  archiveStats,
  clearSavedCases,
  deleteSavedCase,
  listSavedCases,
  loadSavedCase,
} from "../src/archive.mjs";
import {
  _resetSessionsForTests,
  addIncidentNote,
  closeIncident,
  listIncidents,
  openSessionCount,
  startIncident,
  triageIntoIncident,
} from "../src/sessions.mjs";

function ban(title) {
  console.log(`\n══ ${title} ══`);
}

function ok(msg) {
  console.log(`  ✓ ${msg}`);
}

async function main() {
  const dir = await mkdtemp(join(tmpdir(), "stacksentry-c-demo-"));
  process.env.STACKSENTRY_CASES_DIR = dir;
  _resetSessionsForTests();

  console.log("StackSentry storage model C — live test");
  console.log(`Temp archive dir: ${dir}`);

  try {
    ban("1) First incident uses RAM memory");
    const a = startIncident({ title: "Incident A — schema" });
    ok(`opened ${a.id} (openSessionCount=${openSessionCount()})`);
    triageIntoIncident(a.id, 'relation "users" does not exist SQLSTATE 42P01');
    addIncidentNote(a.id, "Note on A");
    ok(`RAM open list: ${listIncidents().map((i) => i.id).join(", ")}`);
    ok(`disk saved so far: ${(await listSavedCases()).length}`);

    ban("2) Close A → store on disk, clear from RAM");
    const closedA = await closeIncident(a.id);
    ok(`archived bytes=${closedA.archive.bytes}`);
    ok(`RAM open count after close: ${openSessionCount()}`);
    ok(`disk cases: ${(await listSavedCases()).map((c) => c.id).join(", ")}`);

    ban("3) Next incident uses fresh RAM (does not reload A)");
    const b = startIncident({ title: "Incident B — refused" });
    triageIntoIncident(b.id, "connect ECONNREFUSED 127.0.0.1:5432");
    ok(`opened ${b.id}`);
    ok(`RAM open: ${listIncidents().map((i) => `${i.id}:${i.latestCategory}`).join(", ")}`);
    ok(`A is NOT in RAM: ${!listIncidents().some((i) => i.id === a.id)}`);
    const loadedA = await loadSavedCase(a.id);
    ok(`A still on disk: category=${loadedA.latest.category}`);

    ban("4) Close B → second archive");
    await closeIncident(b.id);
    const saved = await listSavedCases();
    ok(`disk cases (${saved.length}): ${saved.map((c) => `${c.id}(${c.latestCategory})`).join(", ")}`);
    ok(`RAM empty: openSessionCount=${openSessionCount()}`);

    ban("5) Third incident again uses clean RAM memory");
    const c = startIncident({ title: "Incident C — timeout" });
    triageIntoIncident(c.id, "upstream ETIMEDOUT after 10000ms");
    ok(`only C in RAM: ${listIncidents().map((i) => i.latestCategory).join(",")}`);
    await closeIncident(c.id);

    ban("6) archive_stats");
    const stats = await archiveStats();
    ok(`count=${stats.count} totalBytes=${stats.totalBytes} (~${stats.totalKB} KB)`);
    ok(`dir=${stats.casesDir}`);

    ban("7) delete one case");
    await deleteSavedCase(a.id);
    ok(`after delete A: ${(await listSavedCases()).map((x) => x.id).join(", ") || "(none left among deleted)"}`);
    ok(`remaining count=${(await listSavedCases()).length}`);

    ban("8) clear_saved_cases — wipe disk archive");
    const cleared = await clearSavedCases();
    ok(`removed=${cleared.removed} bytesFreed=${cleared.bytesFreed}`);
    ok(`disk empty: ${(await listSavedCases()).length === 0}`);

    ban("9) Next incident after clear still uses RAM normally");
    const d = startIncident({ title: "Incident D — after clear" });
    triageIntoIncident(d.id, "statusCode: 429 Too Many Requests");
    ok(`D in RAM category=${listIncidents()[0].latestCategory}`);
    await closeIncident(d.id);
    ok(`D archived again; disk count=${(await listSavedCases()).length}`);
    await clearSavedCases();

    console.log("\nAll storage model C cases passed.\n");
  } finally {
    _resetSessionsForTests();
    delete process.env.STACKSENTRY_CASES_DIR;
    await rm(dir, { recursive: true, force: true });
  }
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
