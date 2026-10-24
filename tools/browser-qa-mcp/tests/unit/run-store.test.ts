import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { randomUUID } from "node:crypto";
import { RunStore, isValidRunId } from "../../src/runner/run-store.js";
import { writeReport } from "../../src/reports/json-reporter.js";
import { mkdirSync } from "node:fs";
import type { RunResult } from "../../src/types/test-plan.js";

const MEM_ID = "11111111-1111-4111-8111-111111111111";
const DISK_ID = "22222222-2222-4222-8222-222222222222";

let baseDir: string;

beforeEach(() => {
  baseDir = mkdtempSync(path.join(tmpdir(), "browser-qa-mcp-run-store-"));
});

afterEach(() => {
  rmSync(baseDir, { recursive: true, force: true });
});

function makeResult(runId: string): RunResult {
  return {
    runId,
    planName: "demo",
    baseUrl: "http://127.0.0.1:4000",
    startedAt: "2026-01-01T00:00:00.000Z",
    finishedAt: "2026-01-01T00:00:01.000Z",
    status: "PASS",
    tests: [],
  };
}

describe("RunStore", () => {
  it("returns a run saved in memory", () => {
    const store = new RunStore(baseDir);
    const result = makeResult(MEM_ID);
    store.save(result);
    expect(store.get(MEM_ID)).toEqual(result);
  });

  it("falls back to reading report.json from disk for an uncached run", () => {
    const result = makeResult(DISK_ID);
    const runDir = path.join(baseDir, DISK_ID);
    mkdirSync(runDir, { recursive: true });
    writeReport(result, path.join(runDir, "report.json"));

    const store = new RunStore(baseDir);
    expect(store.get(DISK_ID)).toEqual(result);
  });

  it("returns undefined for an unknown runId", () => {
    const store = new RunStore(baseDir);
    expect(store.get("does-not-exist")).toBeUndefined();
  });

  it("rejects runIds that are not UUIDs without touching the filesystem", () => {
    const store = new RunStore(baseDir);
    for (const bad of ["../etc", "..", "a/b", "../../" + DISK_ID, DISK_ID + "/..", ""]) {
      expect(isValidRunId(bad)).toBe(false);
      expect(store.get(bad)).toBeUndefined();
    }
  });

  it("bounds its in-memory cache", () => {
    const store = new RunStore(baseDir);
    const ids = Array.from({ length: 101 }, () => randomUUID());
    ids.forEach((id) => store.save(makeResult(id)));
    expect(store.get(ids[0])).toBeUndefined();
    expect(store.get(ids[100])).toBeDefined();
  });
});
