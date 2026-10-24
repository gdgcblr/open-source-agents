import type { Page } from "playwright";
import type { TestStep } from "../planner/schema.js";
import { DEFAULT_STEP_TIMEOUT_MS } from "../planner/schema.js";
import type { TargetPolicy } from "../security/target-policy.js";

export class ActionBlockedError extends Error {}

export interface ActionContext {
  page: Page;
  baseUrl: string;
  targetPolicy: TargetPolicy;
  screenshotDir: string;
  testId: string;
}

export interface ActionOutcome {
  message: string;
  screenshotPath?: string;
}

/**
 * Executes a single non-assertion action. Deliberately exposes only the
 * fixed set of actions below - no arbitrary JS execution, no filesystem
 * access, no raw CDP/browser commands.
 */
export async function executeAction(step: TestStep, ctx: ActionContext): Promise<ActionOutcome> {
  const timeout = step.timeoutMs ?? DEFAULT_STEP_TIMEOUT_MS;

  switch (step.action) {
    case "navigate": {
      const target = new URL(step.url!, ctx.baseUrl).toString();
      const verdict = await ctx.targetPolicy.evaluateResolved(target);
      if (!verdict.allowed) {
        throw new ActionBlockedError(verdict.reason ?? `Navigation to "${target}" is not allowed`);
      }
      await ctx.page.goto(target, { timeout });
      return { message: `Navigated to ${target}` };
    }

    case "click": {
      await ctx.page.locator(step.selector!).click({ timeout });
      return { message: `Clicked "${step.selector}"` };
    }

    case "fill": {
      await ctx.page.locator(step.selector!).fill(step.value ?? "", { timeout });
      return { message: `Filled "${step.selector}"` };
    }

    case "select_option": {
      await ctx.page.locator(step.selector!).selectOption(step.option ?? "", { timeout });
      return { message: `Selected "${step.option}" on "${step.selector}"` };
    }

    case "check": {
      await ctx.page.locator(step.selector!).check({ timeout });
      return { message: `Checked "${step.selector}"` };
    }

    case "uncheck": {
      await ctx.page.locator(step.selector!).uncheck({ timeout });
      return { message: `Unchecked "${step.selector}"` };
    }

    case "wait_for_element": {
      await ctx.page.locator(step.selector!).waitFor({ state: "visible", timeout });
      return { message: `Waited for "${step.selector}"` };
    }

    case "capture_screenshot": {
      const path = `${ctx.screenshotDir}/${ctx.testId}-${Date.now()}.png`;
      await ctx.page.screenshot({ path });
      return { message: "Captured screenshot", screenshotPath: path };
    }

    default:
      throw new Error(`"${step.action}" is not an executable action (it is an assertion)`);
  }
}
