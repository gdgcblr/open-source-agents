import type { GenerateOptions, ModelProvider } from "./model-provider.js";

type FetchLike = typeof fetch;

/**
 * Local/open-weights models (e.g. Gemma) served by Ollama.
 * Keeps issue and repository data on the user's machine.
 */
export class OllamaProvider implements ModelProvider {
  readonly providerName = "ollama";

  constructor(
    readonly modelName: string,
    private readonly host = "http://localhost:11434",
    private readonly fetchImpl: FetchLike = fetch,
  ) {}

  async generateText(prompt: string, options: GenerateOptions = {}): Promise<string> {
    let response: Response;
    try {
      response = await this.fetchImpl(`${this.host.replace(/\/$/, "")}/api/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: this.modelName,
          prompt,
          stream: false,
          ...(options.json ? { format: "json" } : {}),
        }),
      });
    } catch (error) {
      throw new Error(
        `Could not reach Ollama at ${this.host}. Is it running (\`ollama serve\`) with the model pulled (\`ollama pull ${this.modelName}\`)? ${error instanceof Error ? error.message : ""}`,
      );
    }

    if (!response.ok) {
      throw new Error(`Ollama request failed: ${response.status} ${await response.text()}`.trim());
    }

    const data = (await response.json()) as { response?: string };
    const text = data.response?.trim();
    if (!text) {
      throw new Error("Ollama returned an empty response.");
    }
    return text;
  }
}
