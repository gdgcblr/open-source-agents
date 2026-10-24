/**
 * Minimal, dependency-free LLM provider abstraction used by the optional
 * planner and failure-diagnosis modules. Deterministic test execution
 * (src/runner, src/assertions, src/security) never imports this module -
 * those paths work with zero API keys and zero network calls to a model.
 *
 * Two providers are supported - Anthropic and Gemini - both selected
 * through plain environment variables, with no SDK dependency for either
 * (both call their REST API directly via fetch). Both default to their
 * cheapest/fastest model: this abstraction only drafts a short JSON test
 * plan or summarizes failure evidence, neither of which benefits from a
 * frontier-tier model. See the README's "AI Planner: Model & Pricing
 * Choice" section for the cost comparison behind this default.
 */
export interface LLMProvider {
  complete(prompt: string): Promise<string>;
}

export class AnthropicProvider implements LLMProvider {
  constructor(
    private readonly apiKey: string,
    private readonly model: string = "claude-haiku-5-5",
  ) {}

  async complete(prompt: string): Promise<string> {
    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": this.apiKey,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model: this.model,
        max_tokens: 2000,
        messages: [{ role: "user", content: prompt }],
      }),
    });

    if (!res.ok) {
      throw new Error(`Anthropic API error ${res.status}: ${await res.text()}`);
    }

    const data = (await res.json()) as { content?: Array<{ text?: string }> };
    const text = data.content?.[0]?.text;
    if (typeof text !== "string") {
      throw new Error("Unexpected response shape from the Anthropic API");
    }
    return text;
  }
}

export class GeminiProvider implements LLMProvider {
  constructor(
    private readonly apiKey: string,
    private readonly model: string = "gemini-2.5-flash-lite",
  ) {}

  async complete(prompt: string): Promise<string> {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${this.model}:generateContent?key=${this.apiKey}`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }] }),
    });

    if (!res.ok) {
      throw new Error(`Gemini API error ${res.status}: ${await res.text()}`);
    }

    const data = (await res.json()) as {
      candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }>;
    };
    const text = data.candidates?.[0]?.content?.parts?.[0]?.text;
    if (typeof text !== "string") {
      throw new Error("Unexpected response shape from the Gemini API");
    }
    return text;
  }
}

export function isPlannerConfigured(): boolean {
  return Boolean(process.env.ANTHROPIC_API_KEY || process.env.GEMINI_API_KEY);
}

/**
 * Resolves which provider to use, failing fast and explicitly rather than
 * silently guessing:
 * - LLM_PROVIDER set -> use exactly that provider; error if its key is missing.
 * - LLM_PROVIDER unset, both keys present -> error asking the caller to disambiguate,
 *   rather than silently preferring one provider's bill over the other's.
 * - LLM_PROVIDER unset, exactly one key present -> use that one.
 * - Neither key present -> error (AI features are optional; this is the "not configured" case).
 */
export function getDefaultProvider(): LLMProvider {
  const requested = process.env.LLM_PROVIDER?.toLowerCase();
  const hasAnthropic = Boolean(process.env.ANTHROPIC_API_KEY);
  const hasGemini = Boolean(process.env.GEMINI_API_KEY);

  if (requested === "anthropic") {
    if (!hasAnthropic) throw new Error('LLM_PROVIDER is set to "anthropic" but ANTHROPIC_API_KEY is not set.');
    return new AnthropicProvider(process.env.ANTHROPIC_API_KEY!, process.env.ANTHROPIC_MODEL || "claude-haiku-5-5");
  }
  if (requested === "gemini") {
    if (!hasGemini) throw new Error('LLM_PROVIDER is set to "gemini" but GEMINI_API_KEY is not set.');
    return new GeminiProvider(process.env.GEMINI_API_KEY!, process.env.GEMINI_MODEL || "gemini-2.5-flash-lite");
  }
  if (requested) {
    throw new Error(`Unknown LLM_PROVIDER "${requested}". Set it to "anthropic" or "gemini".`);
  }

  if (hasAnthropic && hasGemini) {
    throw new Error(
      "Both ANTHROPIC_API_KEY and GEMINI_API_KEY are set. Set LLM_PROVIDER=anthropic or LLM_PROVIDER=gemini to choose which one the AI planner/diagnosis features use.",
    );
  }
  if (hasAnthropic) {
    return new AnthropicProvider(process.env.ANTHROPIC_API_KEY!, process.env.ANTHROPIC_MODEL || "claude-haiku-5-5");
  }
  if (hasGemini) {
    return new GeminiProvider(process.env.GEMINI_API_KEY!, process.env.GEMINI_MODEL || "gemini-2.5-flash-lite");
  }

  throw new Error("AI planning/diagnosis is optional and requires either ANTHROPIC_API_KEY or GEMINI_API_KEY to be set.");
}

/** Strips a ```json ... ``` fence if the model wrapped its JSON output in one. */
export function extractJsonBlock(text: string): string {
  const trimmed = text.trim();
  const fenceMatch = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/i);
  return fenceMatch ? fenceMatch[1].trim() : trimmed;
}
