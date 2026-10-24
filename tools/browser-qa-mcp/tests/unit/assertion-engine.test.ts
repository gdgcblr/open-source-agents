import { describe, expect, it } from "vitest";
import {
  AssertionFailedError,
  executeAssertion,
  isAssertionAction,
  type AssertablePage,
} from "../../src/assertions/assertion-engine.js";
import type { TestStep } from "../../src/planner/schema.js";

interface FakeState {
  visible?: Record<string, boolean>;
  text?: Record<string, string>;
  url?: string;
  counts?: Record<string, number>;
  attrs?: Record<string, string | null>;
}

class FakePage implements AssertablePage {
  constructor(private readonly state: FakeState) {}
  async waitForVisible(selector: string): Promise<boolean> {
    return !!this.state.visible?.[selector];
  }
  async getText(selector: string): Promise<string | null> {
    return this.state.text?.[selector] ?? null;
  }
  async waitForTextContains(selector: string): Promise<string | null> {
    return this.state.text?.[selector] ?? null;
  }
  getUrl(): string {
    return this.state.url ?? "";
  }
  async waitForUrl(expected: string): Promise<boolean> {
    return this.getUrl() === expected;
  }
  async countElements(selector: string): Promise<number> {
    return this.state.counts?.[selector] ?? 0;
  }
  async waitForElementCount(selector: string): Promise<number> {
    return this.state.counts?.[selector] ?? 0;
  }
  async getAttribute(selector: string, attribute: string): Promise<string | null> {
    return this.state.attrs?.[`${selector}|${attribute}`] ?? null;
  }
}

function step(partial: Partial<TestStep> & { action: TestStep["action"] }): TestStep {
  return partial as TestStep;
}

describe("isAssertionAction", () => {
  it("identifies assertion vs. action steps", () => {
    expect(isAssertionAction("assert_visible")).toBe(true);
    expect(isAssertionAction("click")).toBe(false);
  });
});

describe("assertion engine", () => {
  it("passes assert_visible when the element is visible", async () => {
    const page = new FakePage({ visible: { "#ok": true } });
    await expect(executeAssertion(step({ action: "assert_visible", selector: "#ok" }), page, "http://x")).resolves.toContain(
      "visible",
    );
  });

  it("fails assert_visible when the element is not visible", async () => {
    const page = new FakePage({ visible: {} });
    await expect(
      executeAssertion(step({ action: "assert_visible", selector: "#missing" }), page, "http://x"),
    ).rejects.toThrow(AssertionFailedError);
  });

  it("passes assert_text when the text contains the expected substring", async () => {
    const page = new FakePage({ text: { "#msg": "Welcome, Ada" } });
    await expect(
      executeAssertion(step({ action: "assert_text", selector: "#msg", expected: "Welcome" }), page, "http://x"),
    ).resolves.toBeDefined();
  });

  it("fails assert_text when the text does not match", async () => {
    const page = new FakePage({ text: { "#msg": "Something else" } });
    await expect(
      executeAssertion(step({ action: "assert_text", selector: "#msg", expected: "Welcome" }), page, "http://x"),
    ).rejects.toThrow(AssertionFailedError);
  });

  it("passes assert_text when expecting empty string and the element's text is legitimately empty", async () => {
    const page = new FakePage({ text: { "#status": "" } });
    await expect(
      executeAssertion(step({ action: "assert_text", selector: "#status", expected: "" }), page, "http://x"),
    ).resolves.toBeDefined();
  });

  it("fails assert_text when the element is not found (distinct from a legitimately empty text)", async () => {
    const page = new FakePage({ text: {} });
    await expect(
      executeAssertion(step({ action: "assert_text", selector: "#missing", expected: "" }), page, "http://x"),
    ).rejects.toThrow(AssertionFailedError);
  });

  it("passes assert_url when the resolved URL matches", async () => {
    const page = new FakePage({ url: "http://127.0.0.1:4000/signup" });
    await expect(
      executeAssertion(step({ action: "assert_url", expected: "/signup" }), page, "http://127.0.0.1:4000"),
    ).resolves.toBeDefined();
  });

  it("fails assert_url when the URL does not match", async () => {
    const page = new FakePage({ url: "http://127.0.0.1:4000/login" });
    await expect(
      executeAssertion(step({ action: "assert_url", expected: "/signup" }), page, "http://127.0.0.1:4000"),
    ).rejects.toThrow(AssertionFailedError);
  });

  it("passes assert_element_count when counts match", async () => {
    const page = new FakePage({ counts: { ".item": 3 } });
    await expect(
      executeAssertion(step({ action: "assert_element_count", selector: ".item", expected: 3 }), page, "http://x"),
    ).resolves.toBeDefined();
  });

  it("fails assert_element_count when counts differ", async () => {
    const page = new FakePage({ counts: { ".item": 2 } });
    await expect(
      executeAssertion(step({ action: "assert_element_count", selector: ".item", expected: 3 }), page, "http://x"),
    ).rejects.toThrow(AssertionFailedError);
  });

  it("passes assert_attribute when the attribute matches", async () => {
    const page = new FakePage({ attrs: { "#field|aria-invalid": "true" } });
    await expect(
      executeAssertion(
        step({ action: "assert_attribute", selector: "#field", attribute: "aria-invalid", expected: "true" }),
        page,
        "http://x",
      ),
    ).resolves.toBeDefined();
  });

  it("fails assert_attribute when the attribute is missing", async () => {
    const page = new FakePage({ attrs: {} });
    await expect(
      executeAssertion(
        step({ action: "assert_attribute", selector: "#field", attribute: "aria-invalid", expected: "true" }),
        page,
        "http://x",
      ),
    ).rejects.toThrow(AssertionFailedError);
  });
});
