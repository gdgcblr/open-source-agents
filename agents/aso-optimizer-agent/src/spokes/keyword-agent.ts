/**
 * Spoke 1 — Keyword Agent
 * =======================
 * Finds the best ASO (App Store Optimization) keywords for the app.
 * Uses the fallback chain: gemini-2.0-flash → gemma-3-27b-it → rule-based.
 */

import { callWithFallback, FallbackResult } from "../shared/fallback";
import { AppListing } from "../shared/types";

const SYSTEM_INSTRUCTION = `You are an expert App Store Optimization (ASO) specialist with 10+ years of experience.
Your task: identify the most effective search keywords for a Google Play Store listing.

Rules:
- Return ONLY a comma-separated list of 15–20 keywords/phrases. Nothing else.
- Mix broad terms (high volume) with long-tail phrases (lower competition).
- Include action keywords users actually type (e.g. "track my expenses", "scan documents free").
- Never repeat the app name as a keyword.
- Never include fake or misleading terms.`;

function ruleBasedKeywords(listing: AppListing): string {
  const base = [
    listing.category.toLowerCase(),
    `${listing.category.toLowerCase()} app`,
    `free ${listing.category.toLowerCase()}`,
    `best ${listing.category.toLowerCase()} app`,
    `${listing.appName.toLowerCase()} app`,
    `${listing.category.toLowerCase()} for ${(listing.targetAudience ?? "everyone").toLowerCase()}`,
    `${listing.category.toLowerCase()} tool`,
    `${listing.category.toLowerCase()} tracker`,
  ];
  return [...new Set(base)].join(", ");
}

export async function runKeywordAgent(listing: AppListing): Promise<FallbackResult> {
  const prompt = `
App Name       : ${listing.appName}
Category       : ${listing.category}
Target Audience: ${listing.targetAudience ?? "General users"}
Current Title  : ${listing.currentTitle}
Current Desc   : ${listing.currentDescription.slice(0, 300)}

Generate 15–20 high-value ASO keywords for this app (comma-separated list only).`.trim();

  return callWithFallback(prompt, SYSTEM_INSTRUCTION, () => ruleBasedKeywords(listing));
}
