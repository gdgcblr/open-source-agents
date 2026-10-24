/**
 * Spoke 3 — Title Agent
 * ======================
 * Generates an optimised Play Store title under 50 characters.
 * Uses the fallback chain: gemini-2.0-flash → gemma-3-27b-it → rule-based.
 */

import { callWithFallback, FallbackResult } from "../shared/fallback";
import { AppListing } from "../shared/types";

const PLAY_STORE_TITLE_LIMIT = 50;

const SYSTEM_INSTRUCTION = `You are an ASO expert who writes high-converting Google Play Store app titles.

Rules (ALL are mandatory):
- STRICT maximum of ${PLAY_STORE_TITLE_LIMIT} characters including spaces.
- Must include the app name.
- Add 1–2 high-value keywords after a dash (–) or pipe (|).
- Make it clear what the app does at a glance.
- No fake superlatives (best, #1, greatest, etc.).
- No exclamation marks.
- Return ONLY the title string. Nothing else. No quotes. No explanation.`;

function ruleBasedTitle(listing: AppListing): string {
  const base = `${listing.appName} – ${listing.category}`;
  return base.length <= PLAY_STORE_TITLE_LIMIT
    ? base
    : listing.appName.slice(0, PLAY_STORE_TITLE_LIMIT - 3) + "...";
}

export async function runTitleAgent(listing: AppListing): Promise<FallbackResult> {
  const prompt = `
App Name       : ${listing.appName}
Category       : ${listing.category}
Current Title  : ${listing.currentTitle} (${listing.currentTitle.length} chars)
Key Features   : ${listing.currentDescription.slice(0, 150)}

Write a new Play Store title. MUST be under ${PLAY_STORE_TITLE_LIMIT} characters. Return only the title.`.trim();

  return callWithFallback(prompt, SYSTEM_INSTRUCTION, () => ruleBasedTitle(listing));
}
