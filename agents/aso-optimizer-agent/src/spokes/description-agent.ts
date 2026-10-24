/**
 * Spoke 2 — Description Agent
 * ============================
 * Rewrites the Play Store description to maximise conversions.
 * Uses the fallback chain: gemini-2.0-flash → gemma-3-27b-it → rule-based.
 */

import { callWithFallback, FallbackResult } from "../shared/fallback";
import { AppListing } from "../shared/types";

const SYSTEM_INSTRUCTION = `You are a professional mobile app copywriter specialising in Google Play Store listings.
Your task: rewrite the app description to maximise downloads and conversion rate.

Rules:
- First 3 lines MUST be a powerful hook (shown before the "Read more" fold).
- Use short bullet points (●) for the top 4–5 features.
- Naturally weave in important keywords — no keyword stuffing.
- Maximum 3 900 characters (Play Store limit is 4 000).
- Use simple, clear language — no jargon.
- End with a compelling call-to-action.
- NEVER include false claims (e.g. "best app ever", "guaranteed", "#1").
- Return ONLY the optimized description. No commentary, no markdown headers.`;

function ruleBasedDescription(listing: AppListing): string {
  return `${listing.appName} — The smarter ${listing.category.toLowerCase()} app for ${(listing.targetAudience ?? "everyone").toLowerCase()}.

Tired of complicated ${listing.category.toLowerCase()} apps? ${listing.appName} keeps things simple, fast, and powerful — exactly the way you need it.

● Built for real users, not tech experts
● Lightning-fast performance on any device
● Clean interface with no unnecessary clutter
● Automatic sync so your data is always up to date
● Regular updates based on user feedback

Perfect for ${(listing.targetAudience ?? "professionals and students").toLowerCase()}, ${listing.appName} fits seamlessly into your daily workflow.

Download ${listing.appName} free today — and get things done the right way.`;
}

export async function runDescriptionAgent(listing: AppListing): Promise<FallbackResult> {
  const prompt = `
App Name        : ${listing.appName}
Category        : ${listing.category}
Target Audience : ${listing.targetAudience ?? "General users"}
Current Desc    :
${listing.currentDescription}

Rewrite the above Play Store description to maximise downloads. Follow all rules precisely.`.trim();

  return callWithFallback(prompt, SYSTEM_INSTRUCTION, () => ruleBasedDescription(listing));
}
