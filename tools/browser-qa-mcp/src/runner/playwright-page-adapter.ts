import type { Page } from "playwright";
import type { AssertablePage } from "../assertions/assertion-engine.js";

/** Adapts a real Playwright Page to the minimal AssertablePage surface. */
export class PlaywrightAssertablePage implements AssertablePage {
  constructor(private readonly page: Page) {}

  async waitForVisible(selector: string, timeoutMs: number): Promise<boolean> {
    try {
      await this.page.locator(selector).first().waitFor({ state: "visible", timeout: timeoutMs });
      return true;
    } catch {
      return false;
    }
  }

  async getText(selector: string): Promise<string | null> {
    return this.page.locator(selector).first().textContent().catch(() => null);
  }

  async waitForTextContains(selector: string, expected: string, timeoutMs: number): Promise<string | null> {
    const deadline = Date.now() + timeoutMs;
    let lastText: string | null = null;
    do {
      lastText = await this.getText(selector);
      if (lastText !== null && lastText.includes(expected)) return lastText;
      await this.page.waitForTimeout(100);
    } while (Date.now() < deadline);
    return lastText;
  }

  getUrl(): string {
    return this.page.url();
  }

  async waitForUrl(expected: string, timeoutMs: number): Promise<boolean> {
    try {
      await this.page.waitForURL((url) => url.toString() === expected, { timeout: timeoutMs });
      return true;
    } catch {
      return false;
    }
  }

  async countElements(selector: string): Promise<number> {
    return this.page.locator(selector).count();
  }

  async waitForElementCount(selector: string, expected: number, timeoutMs: number): Promise<number> {
    const deadline = Date.now() + timeoutMs;
    let count = await this.countElements(selector);
    while (count !== expected && Date.now() < deadline) {
      await this.page.waitForTimeout(100);
      count = await this.countElements(selector);
    }
    return count;
  }

  async getAttribute(selector: string, attribute: string): Promise<string | null> {
    return this.page.locator(selector).first().getAttribute(attribute).catch(() => null);
  }
}
