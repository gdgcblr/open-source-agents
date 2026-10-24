import { describe, expect, it } from "vitest";
import { diagnoseFailure } from "../../src/diagnosis/failure-analyzer.js";
import type { LLMProvider } from "../../src/llm/client.js";
import type { FailureEvidence } from "../../src/evidence/failure-evidence.js";

const EVIDENCE: FailureEvidence = {
  testId: "t-fail",
  testName: "Invalid email is rejected",
  status: "FAIL",
  error: 'Expected "[role=\'alert\']" to be visible within 5000ms, but it was not',
  reproductionSteps: ["navigate -> ok", "fill \"input[name='email']\" -> ok", "click \"button\" -> ok", "assert_visible -> failed"],
  consoleErrors: [],
  networkFailures: [],
  screenshotPaths: ["artifacts/run-1/t-fail-failure-1.png"],
};

describe("diagnoseFailure", () => {
  it("returns a factual, non-model-generated summary with no provider configured", async () => {
    const diagnosis = await diagnoseFailure(EVIDENCE);
    expect(diagnosis.isModelGenerated).toBe(false);
    expect(diagnosis.hypothesis).toBeUndefined();
    expect(diagnosis.summary).toContain("role='alert'");
  });

  it("attaches a labeled hypothesis when a provider is injected", async () => {
    const provider: LLMProvider = {
      complete: async () =>
        JSON.stringify({ hypothesis: "The email validation accepts values without checking for an '@' and domain.", confidence: "medium" }),
    };
    const diagnosis = await diagnoseFailure(EVIDENCE, provider);
    expect(diagnosis.isModelGenerated).toBe(true);
    expect(diagnosis.confidence).toBe("medium");
    expect(diagnosis.hypothesis).toContain("email validation");
  });

  it("falls back to the factual summary if the provider errors", async () => {
    const provider: LLMProvider = {
      complete: async () => {
        throw new Error("network error");
      },
    };
    const diagnosis = await diagnoseFailure(EVIDENCE, provider);
    expect(diagnosis.isModelGenerated).toBe(false);
  });

  it("falls back to the factual summary if the provider returns malformed JSON", async () => {
    const provider: LLMProvider = { complete: async () => "not json" };
    const diagnosis = await diagnoseFailure(EVIDENCE, provider);
    expect(diagnosis.isModelGenerated).toBe(false);
  });
});
