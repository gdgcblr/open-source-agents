/**
 * Fallback Chain
 * ==============
 * Every spoke agent calls an LLM through this module.
 *
 * Chain:  gemini-2.0-flash  →  gemma-3-27b-it  →  rule-based function
 *
 * Rules:
 *  - Each model gets MAX_RETRIES attempts before we fall to the next.
 *  - Each attempt has a hard TIMEOUT_MS deadline.
 *  - The rule-based fallback always succeeds (no network needed).
 *  - The caller supplies the rule-based function so each spoke can
 *    return a meaningful domain-specific fallback.
 */

import { GoogleGenAI } from "@google/genai";
import * as dotenv from "dotenv";
import { ModelUsed } from "./types";

dotenv.config();

// ── Configuration ────────────────────────────────────────────
const FALLBACK_CHAIN: Exclude<ModelUsed, "rule-based">[] = [
  "gemini-3.8-flash",
  "gemini-3.8-flash-lite",
];
const MAX_RETRIES = 2;       // attempts per model before moving on
const TIMEOUT_MS  = 45_000;  // 45 s deadline for conference Wi-Fi

// ── Public types ─────────────────────────────────────────────
export interface FallbackResult {
  content: string;
  modelUsed: ModelUsed;
}

// ── Internal: single model call ──────────────────────────────
async function callModel(
  modelName: string,
  prompt: string,
  systemInstruction: string
): Promise<string> {
  const apiKey = process.env.GEMINI_API_KEY ?? process.env.GOOGLE_API_KEY;
  if (!apiKey) throw new Error("No API key — set GEMINI_API_KEY in .env");

  const ai = new GoogleGenAI({ apiKey });

  const response = await ai.models.generateContent({
    model: modelName,
    contents: prompt,
    config: {
      systemInstruction,
      maxOutputTokens: 1024,
      temperature: 0.7,
    },
  });

  const text = response.text;
  if (!text) throw new Error("Model returned empty response");
  return text;
}

// ── Public: call with fallback chain ─────────────────────────
/**
 * Tries each model in FALLBACK_CHAIN in order.
 * Falls back to ruleBasedFallback() if all models fail.
 *
 * @param prompt             The user/task prompt
 * @param systemInstruction  System-level persona & rules for the model
 * @param ruleBasedFallback  Zero-dependency function that always returns a string
 */
export async function callWithFallback(
  prompt: string,
  systemInstruction: string,
  ruleBasedFallback: () => string
): Promise<FallbackResult> {

  for (const model of FALLBACK_CHAIN) {
    for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
      try {
        console.log(`      🔄 [${model}] attempt ${attempt}/${MAX_RETRIES} ...`);

        const content = await Promise.race([
          callModel(model, prompt, systemInstruction),
          new Promise<never>((_, reject) =>
            setTimeout(() => reject(new Error("Timeout")), TIMEOUT_MS)
          ),
        ]);

        console.log(`      ✅ [${model}] responded`);
        return { content, modelUsed: model };

      } catch (err) {
        console.log(`      ⚠️  [${model}] attempt ${attempt} failed: ${(err as Error).message}`);
      }
    }

    console.log(`      ➡️  Falling back from ${model}...`);
  }

  // All LLM options exhausted — use deterministic rule-based fallback
  console.log("      ⚡ Using rule-based fallback (no API required)");
  return { content: ruleBasedFallback(), modelUsed: "rule-based" };
}
