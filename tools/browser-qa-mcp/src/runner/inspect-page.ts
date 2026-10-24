import { BrowserManager } from "./browser-manager.js";
import type { TargetPolicy } from "../security/target-policy.js";

export interface InteractiveElement {
  tag: string;
  role: string | null;
  accessibleName: string | null;
  selectorHint: string;
}

export interface PageInspection {
  title: string;
  url: string;
  interactiveElements: InteractiveElement[];
}

const MAX_ELEMENTS = 40;
const NAVIGATION_TIMEOUT_MS = 10_000;

/**
 * Read-only reconnaissance: loads a page and reports its title, URL, and a
 * bounded list of interactive elements with a selector hint - enough to write
 * or debug a test plan's selectors, without submitting anything or running
 * arbitrary script.
 */
export async function inspectPage(targetUrl: string, targetPolicy: TargetPolicy): Promise<PageInspection> {
  const verdict = await targetPolicy.evaluateResolved(targetUrl);
  if (!verdict.allowed) {
    throw new Error(verdict.reason ?? `Target "${targetUrl}" is not allowed`);
  }

  const browserManager = new BrowserManager();
  await browserManager.launch();
  try {
    const session = await browserManager.openTestSession(targetPolicy);
    try {
      try {
        await session.page.goto(targetUrl, { timeout: NAVIGATION_TIMEOUT_MS });
      } finally {
        // A redirect the network guard aborted surfaces as a generic net error; report the policy reason instead.
        const blocked = session.networkGuard.takeBlockedNavigation();
        if (blocked) throw new Error(blocked.reason);
      }
      const title = await session.page.title();
      const url = session.page.url();

      const interactiveElements = await session.page
        .locator("a, button, input, select, textarea, [role]")
        .evaluateAll((nodes: HTMLElement[], max: number) =>
          nodes.slice(0, max).map((el) => {
            const tag = el.tagName.toLowerCase();
            const role = el.getAttribute("role");
            const accessibleName =
              el.getAttribute("aria-label") ||
              (el as HTMLInputElement).placeholder ||
              el.textContent?.trim().slice(0, 100) ||
              null;
            const id = el.getAttribute("id");
            const name = el.getAttribute("name");
            const selectorHint = id ? `#${id}` : name ? `${tag}[name="${name}"]` : tag;
            return { tag, role, accessibleName, selectorHint };
          }),
        MAX_ELEMENTS,
        );

      return { title, url, interactiveElements };
    } finally {
      await browserManager.closeTestSession(session);
    }
  } finally {
    await browserManager.close();
  }
}
