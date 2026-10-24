import { readFileSync, writeFileSync } from "node:fs";
import type { RunResult } from "../types/test-plan.js";
import { runResultSchema } from "./report-schema.js";

export function writeReport(result: RunResult, path: string): void {
  writeFileSync(path, JSON.stringify(result, null, 2));
}

/** Reads a previously written report and validates its shape before trusting it. */
export function readReport(path: string): RunResult {
  const raw = JSON.parse(readFileSync(path, "utf-8"));
  return runResultSchema.parse(raw) as RunResult;
}
