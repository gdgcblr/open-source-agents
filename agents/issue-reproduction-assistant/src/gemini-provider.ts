import { GoogleGenAI } from "@google/genai";
import type { GenerateOptions, ModelProvider } from "./model-provider.js";

export class GeminiProvider implements ModelProvider {
  readonly providerName = "gemini";
  private readonly client: GoogleGenAI;

  constructor(
    readonly modelName: string,
    apiKey: string,
  ) {
    this.client = new GoogleGenAI({ apiKey });
  }

  async generateText(prompt: string, options: GenerateOptions = {}): Promise<string> {
    const response = await this.generateWithRetry(prompt, options);
    const text = response.text?.trim();

    if (!text) {
      throw new Error("Gemini returned an empty response.");
    }

    return text;
  }

  private async generateWithRetry(prompt: string, options: GenerateOptions) {
    const delays = [2_000, 5_000, 10_000];
    for (let attempt = 0; ; attempt += 1) {
      try {
        return await this.client.models.generateContent({
          model: this.modelName,
          contents: prompt,
          config: {
            httpOptions: { timeout: 60_000 },
            ...(options.json ? { responseMimeType: "application/json" } : {}),
          },
        });
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        const transient = /\b(429|500|503|504)\b|UNAVAILABLE|RESOURCE_EXHAUSTED/.test(message);
        if (!transient || attempt >= delays.length) {
          throw error;
        }
        await new Promise((resolve) => setTimeout(resolve, delays[attempt]));
      }
    }
  }
}
