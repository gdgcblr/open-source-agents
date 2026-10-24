import { existsSync } from "node:fs";
import path from "node:path";
import type { RunResult } from "../types/test-plan.js";
import { readReport } from "../reports/json-reporter.js";

const RUN_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MAX_CACHED_RUNS = 100;

/** runIds are always crypto.randomUUID(); anything else never reaches the filesystem. */
export function isValidRunId(runId: string): boolean {
  return RUN_ID_PATTERN.test(runId);
}

/**
 * Looks up a run's report by ID, in memory first, then falling back to the
 * on-disk report.json this process (or an earlier CLI invocation) wrote.
 * Shared by the CLI and the MCP server so both read the same source of truth.
 */
export class RunStore {
  private readonly cache = new Map<string, RunResult>();
  private readonly baseDir: string;

  constructor(baseDir: string) {
    this.baseDir = path.resolve(baseDir);
  }

  save(result: RunResult): void {
    this.cache.delete(result.runId);
    this.cache.set(result.runId, result);
    // Map iteration order is insertion order, so the first key is the oldest.
    while (this.cache.size > MAX_CACHED_RUNS) {
      this.cache.delete(this.cache.keys().next().value!);
    }
  }

  get(runId: string): RunResult | undefined {
    if (!isValidRunId(runId)) return undefined;

    const cached = this.cache.get(runId);
    if (cached) return cached;

    const reportPath = path.resolve(this.baseDir, runId, "report.json");
    if (!reportPath.startsWith(this.baseDir + path.sep)) return undefined;
    if (!existsSync(reportPath)) return undefined;

    const result = readReport(reportPath);
    this.save(result);
    return result;
  }
}
