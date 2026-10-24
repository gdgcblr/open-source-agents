import { mkdirSync, mkdtempSync, rmSync, utimesSync, writeFileSync, existsSync } from "node:fs";
import { randomUUID } from "node:crypto";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { pruneArtifacts, retentionFromEnv } from "../../src/evidence/artifact-retention.js";

let baseDir: string;
const DAY_MS = 24 * 60 * 60 * 1000;

beforeEach(() => {
  baseDir = mkdtempSync(path.join(tmpdir(), "browser-qa-mcp-retention-"));
});

afterEach(() => {
  rmSync(baseDir, { recursive: true, force: true });
});

function makeRun(ageMs: number): string {
  const runId = randomUUID();
  const dir = path.join(baseDir, runId);
  mkdirSync(dir);
  const when = new Date(Date.now() - ageMs);
  utimesSync(dir, when, when);
  return runId;
}

describe("pruneArtifacts", () => {
  it("keeps only the newest maxRuns run directories", () => {
    const oldest = makeRun(3000);
    const middle = makeRun(2000);
    const newest = makeRun(1000);
    expect(pruneArtifacts(baseDir, { maxRuns: 2 })).toEqual([oldest]);
    expect(existsSync(path.join(baseDir, middle))).toBe(true);
    expect(existsSync(path.join(baseDir, newest))).toBe(true);
  });

  it("deletes runs older than maxAgeMs but never a kept run", () => {
    const old = makeRun(10 * DAY_MS);
    const current = makeRun(20 * DAY_MS);
    const fresh = makeRun(0);
    expect(pruneArtifacts(baseDir, { maxAgeMs: 7 * DAY_MS }, { keep: [current] })).toEqual([old]);
    expect(existsSync(path.join(baseDir, fresh))).toBe(true);
  });

  it("never touches entries that are not UUID-named run directories", () => {
    mkdirSync(path.join(baseDir, "not-a-run"));
    writeFileSync(path.join(baseDir, "notes.txt"), "keep me");
    expect(pruneArtifacts(baseDir, { maxRuns: 0, maxAgeMs: 1 }, { now: Date.now() + DAY_MS })).toEqual([]);
    expect(existsSync(path.join(baseDir, "not-a-run"))).toBe(true);
  });

  it("is a no-op for a missing base directory", () => {
    expect(pruneArtifacts(path.join(baseDir, "missing"), { maxRuns: 1 })).toEqual([]);
  });
});

describe("retentionFromEnv", () => {
  it("defaults to 50 runs / 7 days and treats 0 as unlimited", () => {
    expect(retentionFromEnv({})).toEqual({ maxRuns: 50, maxAgeMs: 7 * DAY_MS });
    expect(retentionFromEnv({ QA_ARTIFACTS_MAX_RUNS: "0", QA_ARTIFACTS_MAX_AGE_DAYS: "0" })).toEqual({ maxRuns: 0, maxAgeMs: 0 });
  });
});
