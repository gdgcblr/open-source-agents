import type { Page, Request, Response } from "playwright";
import type { NetworkEvidenceEntry } from "../types/test-plan.js";
import { sanitizeUrl } from "../security/sanitization.js";

const MAX_ENTRIES = 50;

/** Collects failed requests and error-status (>=400) responses for one test. */
export class NetworkCollector {
  private readonly entries: NetworkEvidenceEntry[] = [];

  private readonly onRequestFailed = (request: Request): void => {
    this.record(request.url(), request.method(), undefined, request.failure()?.errorText);
  };

  private readonly onResponse = (response: Response): void => {
    if (response.status() >= 400) {
      this.record(response.url(), response.request().method(), response.status());
    }
  };

  constructor(private readonly page: Page) {
    page.on("requestfailed", this.onRequestFailed);
    page.on("response", this.onResponse);
  }

  private record(url: string, method: string, status?: number, failureText?: string): void {
    if (this.entries.length >= MAX_ENTRIES) return;
    this.entries.push({ url: sanitizeUrl(url), method, status, failureText, timestamp: new Date().toISOString() });
  }

  getEntries(): NetworkEvidenceEntry[] {
    return [...this.entries];
  }

  dispose(): void {
    this.page.off("requestfailed", this.onRequestFailed);
    this.page.off("response", this.onResponse);
  }
}
