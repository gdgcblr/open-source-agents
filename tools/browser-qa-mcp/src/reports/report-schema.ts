import { z } from "zod";

export const stepResultSchema = z.object({
  action: z.string(),
  selector: z.string().optional(),
  status: z.enum(["ok", "failed", "blocked"]),
  message: z.string().optional(),
  durationMs: z.number(),
});

export const consoleEvidenceSchema = z.object({
  type: z.string(),
  text: z.string(),
  timestamp: z.string(),
});

export const networkEvidenceSchema = z.object({
  url: z.string(),
  method: z.string(),
  status: z.number().optional(),
  failureText: z.string().optional(),
  timestamp: z.string(),
});

export const testResultSchema = z.object({
  id: z.string(),
  name: z.string(),
  status: z.enum(["PASS", "FAIL", "BLOCKED"]),
  steps: z.array(stepResultSchema),
  error: z.string().optional(),
  startedAt: z.string(),
  finishedAt: z.string(),
  durationMs: z.number(),
  screenshotPaths: z.array(z.string()),
  consoleErrors: z.array(consoleEvidenceSchema),
  networkFailures: z.array(networkEvidenceSchema),
  tracePath: z.string().optional(),
});

export const runResultSchema = z.object({
  runId: z.string(),
  planName: z.string(),
  baseUrl: z.string(),
  startedAt: z.string(),
  finishedAt: z.string(),
  status: z.enum(["PASS", "FAIL", "BLOCKED"]),
  tests: z.array(testResultSchema),
});

export type RunResultShape = z.infer<typeof runResultSchema>;
