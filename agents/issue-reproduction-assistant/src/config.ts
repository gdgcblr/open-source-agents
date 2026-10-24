import { GeminiProvider } from "./gemini-provider.js";
import type { ModelProvider } from "./model-provider.js";
import { OllamaProvider } from "./ollama-provider.js";

export interface AppConfig {
  provider: string;
  model: string;
  apiKey?: string;
  ollamaHost?: string;
}

type ProviderFactory = (config: AppConfig) => ModelProvider;

const DEFAULT_MODELS: Record<string, string> = {
  gemini: "gemini-3.8-flash",
  ollama: "gemma3",
};

/** Register new providers here; the rest of the agent only sees `ModelProvider`. */
const PROVIDERS: Record<string, ProviderFactory> = {
  gemini(config) {
    if (!config.apiKey) {
      throw new Error("GEMINI_API_KEY is required. Add it to your environment or local .env file.");
    }
    return new GeminiProvider(config.model, config.apiKey);
  },
  ollama(config) {
    return new OllamaProvider(config.model, config.ollamaHost);
  },
};

export function readConfig(env: NodeJS.ProcessEnv = process.env): AppConfig {
  const provider = env.AI_PROVIDER?.trim().toLowerCase() || "gemini";
  return {
    provider,
    model: env.AI_MODEL?.trim() || DEFAULT_MODELS[provider] || DEFAULT_MODELS.gemini,
    apiKey: env.GEMINI_API_KEY,
    ollamaHost: env.OLLAMA_HOST,
  };
}

export function supportedProviders(): string[] {
  return Object.keys(PROVIDERS);
}

export function createProvider(config: AppConfig): ModelProvider {
  const factory = PROVIDERS[config.provider];
  if (!factory) {
    throw new Error(
      `Unsupported AI_PROVIDER "${config.provider}". Supported: ${supportedProviders().join(", ")}.`,
    );
  }
  return factory(config);
}
