import type { TestStep } from "../planner/schema.js";
import { DEFAULT_STEP_TIMEOUT_MS } from "../planner/schema.js";

export class AssertionFailedError extends Error {}

/**
 * The minimal page surface assertions need. Keeping assertion logic behind
 * this interface (rather than calling Playwright directly) lets the pass/fail
 * semantics be unit-tested with an in-memory fake, with no browser involved.
 */
export interface AssertablePage {
  waitForVisible(selector: string, timeoutMs: number): Promise<boolean>;
  getText(selector: string): Promise<string | null>;
  waitForTextContains(selector: string, expected: string, timeoutMs: number): Promise<string | null>;
  getUrl(): string;
  waitForUrl(expected: string, timeoutMs: number): Promise<boolean>;
  countElements(selector: string): Promise<number>;
  waitForElementCount(selector: string, expected: number, timeoutMs: number): Promise<number>;
  getAttribute(selector: string, attribute: string): Promise<string | null>;
}

export function isAssertionAction(action: string): boolean {
  return action.startsWith("assert_");
}

/**
 * Executes a single assertion and returns a human-readable success message,
 * or throws AssertionFailedError describing exactly what was expected vs.
 * observed. A successful action (e.g. a click) is never treated as a pass;
 * only these explicit checks determine test outcome.
 */
export async function executeAssertion(step: TestStep, page: AssertablePage, baseUrl: string): Promise<string> {
  const timeout = step.timeoutMs ?? DEFAULT_STEP_TIMEOUT_MS;

  switch (step.action) {
    case "assert_visible": {
      const ok = await page.waitForVisible(step.selector!, timeout);
      if (!ok) {
        throw new AssertionFailedError(`Expected "${step.selector}" to be visible within ${timeout}ms, but it was not`);
      }
      return `"${step.selector}" is visible`;
    }

    case "assert_text": {
      const expected = String(step.expected ?? "");
      const actual = await page.waitForTextContains(step.selector!, expected, timeout);
      if (actual === null || !actual.includes(expected)) {
        throw new AssertionFailedError(
          `Expected "${step.selector}" text to contain "${expected}", but got "${actual ?? "(element not found)"}"`,
        );
      }
      return `"${step.selector}" text contains "${expected}"`;
    }

    case "assert_url": {
      const expected = new URL(String(step.expected ?? ""), baseUrl).toString();
      const ok = await page.waitForUrl(expected, timeout);
      if (!ok) {
        throw new AssertionFailedError(`Expected URL "${expected}", but current URL is "${page.getUrl()}"`);
      }
      return `URL is "${expected}"`;
    }

    case "assert_element_count": {
      const expected = Number(step.expected);
      const actual = await page.waitForElementCount(step.selector!, expected, timeout);
      if (actual !== expected) {
        throw new AssertionFailedError(`Expected ${expected} element(s) matching "${step.selector}", found ${actual}`);
      }
      return `Found ${expected} element(s) matching "${step.selector}"`;
    }

    case "assert_attribute": {
      const expected = String(step.expected ?? "");
      const actual = await page.getAttribute(step.selector!, step.attribute!);
      if (actual !== expected) {
        throw new AssertionFailedError(
          `Expected attribute "${step.attribute}" on "${step.selector}" to be "${expected}", but got "${actual ?? "(null)"}"`,
        );
      }
      return `Attribute "${step.attribute}" on "${step.selector}" is "${expected}"`;
    }

    default:
      throw new Error(`"${step.action}" is not an assertion`);
  }
}
