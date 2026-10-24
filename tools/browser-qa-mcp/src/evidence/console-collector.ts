import type { ConsoleMessage, Page } from "playwright";
import type { ConsoleEvidenceEntry } from "../types/test-plan.js";
import { sanitizeText } from "../security/sanitization.js";

const MAX_ENTRIES = 50;

/** Collects browser console errors/warnings and uncaught page exceptions for one test. */
export class ConsoleCollector {
  private readonly entries: ConsoleEvidenceEntry[] = [];

  private readonly onConsole = (msg: ConsoleMessage): void => {
    const type = msg.type();
    if (type !== "error" && type !== "warning") return;
    this.record(type, msg.text());
  };

  private readonly onPageError = (err: Error): void => {
    this.record("pageerror", err.message);
  };

  constructor(private readonly page: Page) {
    page.on("console", this.onConsole);
    page.on("pageerror", this.onPageError);
  }

  private record(type: string, text: string): void {
    if (this.entries.length >= MAX_ENTRIES) return;
    this.entries.push({ type, text: sanitizeText(text), timestamp: new Date().toISOString() });
  }

  getEntries(): ConsoleEvidenceEntry[] {
    return [...this.entries];
  }

  dispose(): void {
    this.page.off("console", this.onConsole);
    this.page.off("pageerror", this.onPageError);
  }
}
