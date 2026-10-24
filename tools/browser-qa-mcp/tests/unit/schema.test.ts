import { describe, expect, it } from "vitest";
import { safeValidateTestPlan, validateTestPlan } from "../../src/planner/schema.js";

const basePlan = {
  version: 1,
  name: "demo",
  baseUrl: "http://127.0.0.1:4000",
};

describe("test plan schema", () => {
  it("accepts a well-formed plan", () => {
    const plan = {
      ...basePlan,
      tests: [{ id: "t1", name: "test", steps: [{ action: "navigate", url: "/" }] }],
    };
    expect(() => validateTestPlan(plan)).not.toThrow();
  });

  it("rejects an unsupported action", () => {
    const plan = {
      ...basePlan,
      tests: [{ id: "t1", name: "test", steps: [{ action: "eval_script", value: "alert(1)" }] }],
    };
    expect(safeValidateTestPlan(plan).success).toBe(false);
  });

  it("rejects a click step missing a selector", () => {
    const plan = {
      ...basePlan,
      tests: [{ id: "t1", name: "test", steps: [{ action: "click" }] }],
    };
    expect(safeValidateTestPlan(plan).success).toBe(false);
  });

  it("rejects an assert_text step missing expected", () => {
    const plan = {
      ...basePlan,
      tests: [{ id: "t1", name: "test", steps: [{ action: "assert_text", selector: "#x" }] }],
    };
    expect(safeValidateTestPlan(plan).success).toBe(false);
  });

  it("rejects an id with disallowed characters", () => {
    const plan = {
      ...basePlan,
      tests: [{ id: "bad id!", name: "test", steps: [{ action: "navigate", url: "/" }] }],
    };
    expect(safeValidateTestPlan(plan).success).toBe(false);
  });

  it("enforces the max steps per test limit", () => {
    const steps = Array.from({ length: 31 }, () => ({ action: "navigate", url: "/" }));
    const plan = { ...basePlan, tests: [{ id: "t1", name: "t", steps }] };
    expect(safeValidateTestPlan(plan).success).toBe(false);
  });

  it("enforces the max tests per plan limit", () => {
    const tests = Array.from({ length: 21 }, (_, i) => ({
      id: `t${i}`,
      name: `t${i}`,
      steps: [{ action: "navigate", url: "/" }],
    }));
    expect(safeValidateTestPlan({ ...basePlan, tests }).success).toBe(false);
  });

  it("rejects unknown top-level fields (strict schema)", () => {
    const plan = {
      ...basePlan,
      tests: [{ id: "t1", name: "test", steps: [{ action: "navigate", url: "/" }] }],
      extraField: "not allowed",
    };
    expect(safeValidateTestPlan(plan).success).toBe(false);
  });
});
