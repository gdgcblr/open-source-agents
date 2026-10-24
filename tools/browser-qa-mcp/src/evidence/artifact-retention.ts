import { existsSync, readdirSync, rmSync, statSync } from "node:fs";
import path from "node:path";
import { isValidRunId } from "../runner/run-store.js";

export interface RetentionPolicy {
  /** Keep at most this many run directories (newest first). 0 or undefined = no limit. */
  maxRuns?: number;
  /** Delete run directories older than this. 0 or undefined = no limit. */
  maxAgeMs?: number;
}

const DEFAULT_MAX_RUNS = 50;
const DEFAULT_MAX_AGE_DAYS = 7;
const DAY_MS = 24 * 60 * 60 * 1000;

/** Reads QA_ARTIFACTS_MAX_RUNS / QA_ARTIFACTS_MAX_AGE_DAYS; "0" disables a limit. */
export function retentionFromEnv(env: NodeJS.ProcessEnv = process.env): RetentionPolicy {
  const maxRuns = parseLimit(env.QA_ARTIFACTS_MAX_RUNS, DEFAULT_MAX_RUNS);
  const maxAgeDays = parseLimit(env.QA_ARTIFACTS_MAX_AGE_DAYS, DEFAULT_MAX_AGE_DAYS);
  return { maxRuns, maxAgeMs: maxAgeDays * DAY_MS };
}

function parseLimit(raw: string | undefined, fallback: number): number {
  if (raw === undefined || raw.trim() === "") return fallback;
  const value = Number(raw);
  return Number.isFinite(value) && value >= 0 ? value : fallback;
}

/**
 * Deletes old run directories under baseDir. Only directories named like a
 * runId (UUID) are ever touched, so pointing QA_ARTIFACTS_DIR at a shared
 * folder can't delete unrelated files. Returns the runIds removed.
 */
export function pruneArtifacts(
  baseDir: string,
  policy: RetentionPolicy,
  { keep = [], now = Date.now() }: { keep?: string[]; now?: number } = {},
): string[] {
  if (!existsSync(baseDir)) return [];

  const runs = readdirSync(baseDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && isValidRunId(entry.name))
    .map((entry) => ({ runId: entry.name, mtimeMs: statSync(path.join(baseDir, entry.name)).mtimeMs }))
    .sort((a, b) => b.mtimeMs - a.mtimeMs);

  const removed: string[] = [];
  runs.forEach((run, index) => {
    if (keep.includes(run.runId)) return;
    const overCount = !!policy.maxRuns && index >= policy.maxRuns;
    const tooOld = !!policy.maxAgeMs && now - run.mtimeMs > policy.maxAgeMs;
    if (overCount || tooOld) {
      rmSync(path.join(baseDir, run.runId), { recursive: true, force: true });
      removed.push(run.runId);
    }
  });
  return removed;
}
