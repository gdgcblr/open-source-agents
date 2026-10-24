import { mkdirSync } from "node:fs";
import path from "node:path";

/** Owns the on-disk layout for one run's artifacts: screenshots, traces, and the final report. */
export class ArtifactManager {
  readonly runDir: string;

  constructor(baseDir: string, runId: string) {
    this.runDir = path.join(baseDir, runId);
    mkdirSync(this.runDir, { recursive: true });
  }

  screenshotPath(testId: string, label: string): string {
    return path.join(this.runDir, `${testId}-${label}-${Date.now()}.png`);
  }

  tracePath(testId: string): string {
    return path.join(this.runDir, `${testId}-trace.zip`);
  }

  reportPath(): string {
    return path.join(this.runDir, "report.json");
  }
}
