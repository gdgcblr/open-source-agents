/**
 * Shared TypeScript types for the ASO Optimizer Agent.
 * All agents (hub + spokes) share these interfaces.
 */

/** The raw input provided by the developer about their app */
export interface AppListing {
  appName: string;
  currentTitle: string;
  currentDescription: string;
  category: string;
  targetAudience?: string;
}

/** Which model actually handled the request */
export type ModelUsed = "gemini-3.8-flash" | "gemini-3.8-flash-lite" | "rule-based";

/** Result returned by each spoke agent */
export interface SpokeResult {
  success: boolean;
  content: string;
  modelUsed: ModelUsed;
  error?: string;
}

/** Final report produced by the hub orchestrator */
export interface ASOReport {
  appName: string;
  optimizedTitle: SpokeResult;
  optimizedDescription: SpokeResult;
  keywords: SpokeResult;
  guardrailNotes: string[];
  summary: string;
}

/** Result from any guardrail check */
export interface GuardrailResult {
  safe: boolean;
  reason?: string;
  warnings: string[];
}
