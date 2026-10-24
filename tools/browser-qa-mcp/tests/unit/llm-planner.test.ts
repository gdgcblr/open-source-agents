import { describe, expect, it } from "vitest";
import { planTestFromDescription } from "../../src/planner/llm-planner.js";
import type { LLMProvider } from "../../src/llm/client.js";

function fakeProvider(response: string): LLMProvider {
  return { complete: async () => response };
}

const VALID_PLAN = {
  version: 1,
  name: "Generated plan",
  baseUrl: "http://127.0.0.1:4000",
  tests: [
    {
      id: "t1",
      name: "Generated test",
      steps: [{ action: "navigate", url: "/" }],
    },
  ],
};

describe("planTestFromDescription", () => {
  it("accepts a valid plan returned by the provider", async () => {
    const provider = fakeProvider(JSON.stringify(VALID_PLAN));
    const plan = await planTestFromDescription("test the homepage", "http://127.0.0.1:4000", provider);
    expect(plan.name).toBe("Generated plan");
  });

  it("strips a markdown code fence around the JSON", async () => {
    const provider = fakeProvider("```json\n" + JSON.stringify(VALID_PLAN) + "\n```");
    const plan = await planTestFromDescription("test the homepage", "http://127.0.0.1:4000", provider);
    expect(plan.tests).toHaveLength(1);
  });

  it("rejects a plan using an unsupported action", async () => {
    const badPlan = { ...VALID_PLAN, tests: [{ id: "t1", name: "t", steps: [{ action: "eval_script", value: "x" }] }] };
    const provider = fakeProvider(JSON.stringify(badPlan));
    await expect(planTestFromDescription("do something", "http://127.0.0.1:4000", provider)).rejects.toThrow(
      /schema validation/,
    );
  });

  it("rejects a plan whose baseUrl does not match the requested baseUrl", async () => {
    const redirected = { ...VALID_PLAN, baseUrl: "https://attacker.example" };
    const provider = fakeProvider(JSON.stringify(redirected));
    await expect(planTestFromDescription("test it", "http://127.0.0.1:4000", provider)).rejects.toThrow(
      /does not match the requested baseUrl/,
    );
  });

  it("rejects a non-JSON response", async () => {
    const provider = fakeProvider("I can't help with that.");
    await expect(planTestFromDescription("test it", "http://127.0.0.1:4000", provider)).rejects.toThrow(
      /did not return valid JSON/,
    );
  });
});
