/**
 * Hub Orchestrator
 * ================
 * The central controller in the Hub & Spoke architecture.
 *
 * Responsibilities:
 *  1. Run the INPUT GUARDRAIL on the developer's app listing.
 *  2. Fan out to all three spoke agents IN PARALLEL (keyword, description, title).
 *  3. Run the OUTPUT GUARDRAIL on the combined results.
 *  4. Assemble and return the final ASOReport.
 *
 * The hub never calls an LLM directly — it delegates all model calls
 * to the spokes, each of which uses the shared fallback chain.
 *
 * Topology:
 *
 *   [Developer Input]
 *         │
 *   ┌─────▼─────────────────────────┐
 *   │   INPUT GUARDRAIL             │
 *   │   (hub responsibility)        │
 *   └─────┬─────────────────────────┘
 *         │  passes
 *   ┌─────▼─────────────────────────┐
 *   │   HUB ORCHESTRATOR            │
 *   │   (fans out in parallel)      │
 *   └──┬──────────┬─────────────┬───┘
 *      │          │             │
 *  [Spoke 1]  [Spoke 2]    [Spoke 3]
 *  Keywords   Description   Title
 *  (Gemini→   (Gemini→      (Gemini→
 *   Gemma→     Gemma→        Gemma→
 *   rules)     rules)        rules)
 *      │          │             │
 *   ┌──▼──────────▼─────────────▼───┐
 *   │   OUTPUT GUARDRAIL            │
 *   │   (hub responsibility)        │
 *   └─────┬─────────────────────────┘
 *         │
 *   [ASOReport → Developer]
 */

import { AppListing, ASOReport, SpokeResult } from "../shared/types";
import { inputGuardrail, outputGuardrail } from "../guardrails";
import { runKeywordAgent }     from "../spokes/keyword-agent";
import { runDescriptionAgent } from "../spokes/description-agent";
import { runTitleAgent }       from "../spokes/title-agent";

// ── Helpers ───────────────────────────────────────────────────

function separator(label: string) {
  const line = "─".repeat(60);
  console.log(`\n${line}`);
  console.log(`  ${label}`);
  console.log(line);
}

// ── Hub ───────────────────────────────────────────────────────

/**
 * Entry point for the hub.
 * Returns a complete ASOReport, or null if the input guardrail blocks the request.
 */
export async function runHubOrchestrator(listing: AppListing): Promise<ASOReport | null> {

  console.log("\n" + "═".repeat(60));
  console.log("  🏠 HUB AGENT  —  ASO Optimizer Pipeline");
  console.log("  Architecture: Hub & Spoke │ Fallback: Gemini→Gemma→Rules");
  console.log("═".repeat(60));

  // ── Step 1: Input Guardrail ──────────────────────────────────
  separator("Step 1 of 3  │  🛡️  Input Guardrail");

  const inputCheck = inputGuardrail(listing);

  if (!inputCheck.safe) {
    console.log(`\n${inputCheck.reason}`);
    console.log("\n❌ Pipeline aborted by input guardrail.");
    return null;
  }

  inputCheck.warnings.forEach(w => console.log(`  ${w}`));
  console.log("\n  ✅ Input guardrail passed — dispatching to spokes.");

  // ── Step 2: Fan-out to Spokes (parallel) ─────────────────────
  separator("Step 2 of 3  │  🔀 Spoke Agents  (running in parallel)");
  console.log("  ├── 🗝️  Spoke 1: Keyword Agent");
  console.log("  ├── 📝 Spoke 2: Description Agent");
  console.log("  └── 🏷️  Spoke 3: Title Agent\n");

  const [kwSettled, descSettled, titleSettled] = await Promise.allSettled([
    runKeywordAgent(listing),
    runDescriptionAgent(listing),
    runTitleAgent(listing),
  ]);

  // Normalise settled results into SpokeResult objects
  const toSpokeResult = (
    settled: PromiseSettledResult<Awaited<ReturnType<typeof runKeywordAgent>>>
  ): SpokeResult =>
    settled.status === "fulfilled"
      ? { success: true,  content: settled.value.content, modelUsed: settled.value.modelUsed }
      : { success: false, content: "",                    modelUsed: "rule-based", error: String((settled as PromiseRejectedResult).reason) };

  const keywords    = toSpokeResult(kwSettled);
  const description = toSpokeResult(descSettled);
  const title       = toSpokeResult(titleSettled);

  // ── Step 3: Output Guardrail ─────────────────────────────────
  separator("Step 3 of 3  │  🛡️  Output Guardrail");

  const outputCheck = outputGuardrail(title.content, description.content, keywords.content);
  const guardrailNotes: string[] = [...inputCheck.warnings, ...outputCheck.warnings];

  if (!outputCheck.safe) {
    console.log(`\n  ${outputCheck.reason}`);
    guardrailNotes.push(outputCheck.reason ?? "Output guardrail failed.");
    // We still return the report so the caller knows what happened
  } else {
    outputCheck.warnings.forEach(w => console.log(`  ${w}`));
    console.log("\n  ✅ Output guardrail passed.");
  }

  // ── Assemble Report ──────────────────────────────────────────
  const report: ASOReport = {
    appName: listing.appName,
    optimizedTitle:       title,
    optimizedDescription: description,
    keywords,
    guardrailNotes,
    summary:
      `Models used — ` +
      `Title: ${title.modelUsed} | ` +
      `Description: ${description.modelUsed} | ` +
      `Keywords: ${keywords.modelUsed}`,
  };

  return report;
}
