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
    const response = await this.client.models.generateContent({
      model: this.modelName,
      contents: prompt,
      config: options.json ? { responseMimeType: "application/json" } : undefined,
    });
    const text = response.text?.trim();

    if (!text) {
      throw new Error("Gemini returned an empty response.");
    }

    return text;
  }
}
