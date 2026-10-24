import type { FailureEvidence } from "../evidence/failure-evidence.js";
import { extractJsonBlock, getDefaultProvider, isPlannerConfigured, type LLMProvider } from "../llm/client.js";

export interface FailureDiagnosis {
  testId: string;
  summary: string;
  /** A model-generated causal hypothesis, grounded in the evidence given - never a verified finding. */
  hypothesis?: string;
  confidence?: "low" | "medium" | "high";
  reproductionSteps: string[];
  isModelGenerated: boolean;
}

const DIAGNOSIS_INSTRUCTIONS = `You are given evidence from a failed browser QA test: the assertion error, the step-by-step reproduction, captured console errors, and failed network requests. Respond with ONLY a JSON object: { "hypothesis": string, "confidence": "low"|"medium"|"high" }. The hypothesis must be grounded in the evidence given - do not invent causes the evidence does not support. If the evidence is insufficient to point to a specific cause, set confidence to "low" and say so plainly in the hypothesis text rather than guessing.`;

/**
 * Produces an evidence-based failure summary. Without a configured LLM
 * provider, this returns only the factual evidence (no causal claim) -
 * it never fabricates a "likely cause" on its own. With a provider, the
 * model's hypothesis is returned alongside the facts, explicitly flagged
 * as model-generated so a caller can never mistake it for a verified result.
 */
export async function diagnoseFailure(evidence: FailureEvidence, provider?: LLMProvider): Promise<FailureDiagnosis> {
  const base: FailureDiagnosis = {
    testId: evidence.testId,
    summary: evidence.error ?? "The test did not complete successfully.",
    reproductionSteps: evidence.reproductionSteps,
    isModelGenerated: false,
  };

  if (!provider && !isPlannerConfigured()) {
    return base;
  }

  try {
    const activeProvider = provider ?? getDefaultProvider();
    const prompt = `${DIAGNOSIS_INSTRUCTIONS}\n\nEvidence:\n${JSON.stringify(evidence, null, 2)}`;
    const raw = await activeProvider.complete(prompt);
    const parsed = JSON.parse(extractJsonBlock(raw)) as { hypothesis?: unknown; confidence?: unknown };
    const confidence =
      parsed.confidence === "low" || parsed.confidence === "medium" || parsed.confidence === "high"
        ? parsed.confidence
        : undefined;

    return {
      ...base,
      hypothesis: typeof parsed.hypothesis === "string" ? parsed.hypothesis : undefined,
      confidence,
      isModelGenerated: true,
    };
  } catch {
    // Diagnosis is best-effort and optional; the factual evidence-only summary is still returned.
    return base;
  }
}
