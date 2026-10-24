import { chromium, type Browser, type BrowserContext, type Page } from "playwright";
import { NetworkGuard } from "../security/network-guard.js";
import type { TargetPolicy } from "../security/target-policy.js";

export interface TestSession {
  context: BrowserContext;
  page: Page;
  networkGuard: NetworkGuard;
}

/**
 * Owns one Chromium process for an entire run and hands out a fresh,
 * isolated BrowserContext per test - so one test's cookies, storage, or
 * crashed state can never leak into the next, without paying the cost of a
 * full browser relaunch for every test in the plan.
 */
export class BrowserManager {
  private browser: Browser | undefined;

  async launch(): Promise<void> {
    // Optional override for environments (CI images, sandboxes) that ship a
    // pre-installed Chromium instead of letting `playwright install` download one.
    const executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined;
    this.browser = await chromium.launch({ headless: true, executablePath });
  }

  async openTestSession(targetPolicy: TargetPolicy): Promise<TestSession> {
    if (!this.browser) {
      throw new Error("BrowserManager.launch() must be called before openTestSession()");
    }
    // Service workers can issue requests that context.route() never sees.
    const context = await this.browser.newContext({ serviceWorkers: "block" });
    const networkGuard = new NetworkGuard(targetPolicy);
    try {
      await networkGuard.install(context);
    } catch (err) {
      await context.close().catch(() => {});
      throw err;
    }
    const page = await context.newPage();
    return { context, page, networkGuard };
  }

  async closeTestSession(session: TestSession): Promise<void> {
    await session.context.close().catch(() => {});
  }

  async close(): Promise<void> {
    await this.browser?.close().catch(() => {});
    this.browser = undefined;
  }
}
