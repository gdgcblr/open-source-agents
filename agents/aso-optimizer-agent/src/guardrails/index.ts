/**
 * Guardrails
 * ==========
 * Two safety layers enforced by the Hub before and after spoke execution.
 *
 * INPUT  GUARDRAIL  — runs on the developer's app listing before any LLM call.
 * OUTPUT GUARDRAIL  — runs on the optimized results before returning to user.
 *
 * Philosophy: block clearly harmful content; warn about misleading claims
 * rather than hard-blocking so the agent can still fix them in the output.
 */

import { AppListing, GuardrailResult } from "../shared/types";

// ── Pattern Lists ─────────────────────────────────────────────

/** Hard block — app listing promotes harmful or deceptive products */
const HARMFUL_INPUT_PATTERNS: RegExp[] = [
  /\bspy(ware)?\b/i,
  /\bstalk(er|ing)?\b/i,
  /\bstealth (track|monitor)\b/i,
  /\bhacking tool\b/i,
  /\bcredential.{0,10}(steal|dump|harvest)\b/i,
  /\bnsfw\b/i,
];

/** Soft warn — false advertising that should be removed in output */
const MISLEADING_CLAIMS: Array<{ pattern: RegExp; label: string }> = [
  { pattern: /\b(#1|number one) (app|tool)\b/i,                    label: '"#1 app" superlative'          },
  { pattern: /\bbest app (in the world|ever|of all time)\b/i,       label: '"best app ever" superlative'   },
  { pattern: /\b100% (free|safe|secure|accurate|guaranteed)\b/i,    label: '"100% guaranteed" false claim'  },
  { pattern: /\bguaranteed results?\b/i,                            label: '"guaranteed results" claim'    },
  { pattern: /\bget rich\b/i,                                       label: '"get rich" claim'              },
  { pattern: /\blose \d+ (kg|lbs?|pounds?) (fast|overnight|quickly)\b/i, label: 'false weight-loss claim' },
  { pattern: /\bmake \$\d+ (a day|per day|daily)\b/i,               label: 'false income claim'           },
];

/** Play Store title hard character limit */
const PLAY_STORE_TITLE_LIMIT = 50;

// ── Input Guardrail ───────────────────────────────────────────
/**
 * Checks the developer's ORIGINAL listing before sending to any LLM.
 * Returns safe=false to abort the pipeline for harmful content.
 * Returns warnings for fixable issues (misleading claims, long title).
 */
export function inputGuardrail(listing: AppListing): GuardrailResult {
  const warnings: string[] = [];
  const fullText = `${listing.appName} ${listing.currentTitle} ${listing.currentDescription}`;

  // Hard block — harmful content
  for (const pattern of HARMFUL_INPUT_PATTERNS) {
    if (pattern.test(fullText)) {
      return {
        safe: false,
        reason: `🚫 INPUT GUARDRAIL BLOCKED: Listing contains restricted content (${pattern}). Cannot optimize.`,
        warnings,
      };
    }
  }

  // Minimum description length
  if (listing.currentDescription.trim().length < 30) {
    return {
      safe: false,
      reason: "🚫 INPUT GUARDRAIL BLOCKED: Description is too short (< 30 chars). Please provide a real description.",
      warnings,
    };
  }

  // Soft warnings — misleading claims (will be removed during optimization)
  for (const { pattern, label } of MISLEADING_CLAIMS) {
    if (pattern.test(fullText)) {
      warnings.push(`⚠️  Misleading claim detected (${label}) — will be removed in the optimized output.`);
    }
  }

  // Title too long warning
  if (listing.currentTitle.length > PLAY_STORE_TITLE_LIMIT) {
    warnings.push(
      `⚠️  Current title is ${listing.currentTitle.length} chars. ` +
      `Play Store limit is ${PLAY_STORE_TITLE_LIMIT} — will be shortened.`
    );
  }

  return { safe: true, warnings };
}

// ── Output Guardrail ──────────────────────────────────────────
/**
 * Validates the OPTIMIZED content before presenting to the developer.
 * Hard-blocks if the title exceeds the Play Store limit.
 * Warns if misleading claims crept back into the output.
 */
export function outputGuardrail(
  title: string,
  description: string,
  keywords: string
): GuardrailResult {
  const warnings: string[] = [];

  // Hard block — title exceeds Play Store limit
  if (title.trim().length > PLAY_STORE_TITLE_LIMIT) {
    return {
      safe: false,
      reason:
        `🚫 OUTPUT GUARDRAIL BLOCKED: Optimized title is ${title.trim().length} chars ` +
        `(Play Store max = ${PLAY_STORE_TITLE_LIMIT}). Re-running title agent...`,
      warnings,
    };
  }

  // Hard block — no keywords generated
  if (!keywords || keywords.trim().length === 0) {
    return {
      safe: false,
      reason: "🚫 OUTPUT GUARDRAIL BLOCKED: Keyword agent returned empty output. Re-running...",
      warnings,
    };
  }

  // Soft warn — misleading claims in optimized output
  const outputText = `${title} ${description}`;
  for (const { pattern, label } of MISLEADING_CLAIMS) {
    if (pattern.test(outputText)) {
      warnings.push(`⚠️  OUTPUT GUARDRAIL: Removed misleading claim (${label}) from optimized text.`);
    }
  }

  return { safe: true, warnings };
}
