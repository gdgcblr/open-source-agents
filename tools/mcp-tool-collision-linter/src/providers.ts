import { TfIdfIndex, tokenize, toolText } from "./similarity.js";
import type { LoadedTool, Provider, ToolChoiceRequest } from "./types.js";

const ROUTER_SYSTEM =
  "You are an assistant connected to several tool servers. For the user's request, call the single tool " +
  "that best fulfils it. Fill in arguments as best you can; they are not executed.";

export interface ProviderOptions {
  model?: string;
  apiKey?: string;
  baseUrl?: string;
  temperature?: number;
  maxRetries?: number;
  fetchImpl?: typeof fetch;
}

class HttpError extends Error {
  constructor(
    readonly status: number,
    readonly body: string,
  ) {
    super(`HTTP ${status}: ${body.slice(0, 500)}`);
  }
}

async function postJson(
  url: string,
  headers: Record<string, string>,
  body: unknown,
  opts: { maxRetries: number; fetchImpl: typeof fetch },
): Promise<any> {
  let attempt = 0;
  for (;;) {
    let res: Response;
    try {
      res = await opts.fetchImpl(url, {
        method: "POST",
        headers: { "content-type": "application/json", ...headers },
        body: JSON.stringify(body),
      });
    } catch (err: any) {
      const cause = err?.cause?.message ? ` (${err.cause.message})` : "";
      throw new Error(`Failed to reach ${url}: ${err?.message ?? "network error"}${cause}. Check that your server is running and reachable.`);
    }
    if (res.ok) return res.json();
    const text = await res.text();
    const retryable = res.status === 429 || res.status === 529 || res.status >= 500;
    if (!retryable || attempt >= opts.maxRetries) throw new HttpError(res.status, text);
    const retryAfter = Number(res.headers.get("retry-after"));
    const delay = Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter * 1000 : 500 * 2 ** attempt;
    await new Promise((r) => setTimeout(r, Math.min(delay, 20_000)));
    attempt++;
  }
}

function schemaFor(t: LoadedTool): Record<string, unknown> {
  const s = t.inputSchema;
  return s && (s as { type?: unknown }).type === "object" ? s : { type: "object", properties: {}, ...s };
}

/**
 * No model at all: routes each prompt to the tool whose text overlaps it most.
 * Good for smoke tests, CI without secrets, and seeing the pipeline work. Not a substitute for a real model.
 */
export class OfflineProvider implements Provider {
  readonly name = "offline (lexical router)";
  private cache = new WeakMap<LoadedTool[], TfIdfIndex>();

  async chooseTool({ prompt, tools }: ToolChoiceRequest): Promise<string | null> {
    let index = this.cache.get(tools);
    if (!index) {
      index = new TfIdfIndex(tools.map((t) => tokenize(toolText(t))));
      this.cache.set(tools, index);
    }
    const q = index.vectorize(tokenize(prompt));
    let best = -1;
    let bestScore = 0;
    index.vectors.forEach((v, i) => {
      const s = TfIdfIndex.cosine(q, v);
      if (s > bestScore) {
        bestScore = s;
        best = i;
      }
    });
    return best >= 0 ? tools[best]!.id : null;
  }
}

export class AnthropicProvider implements Provider {
  readonly name: string;
  private readonly model: string;
  private readonly apiKey: string;
  private readonly baseUrl: string;

  constructor(private readonly opts: ProviderOptions = {}) {
    this.model = opts.model ?? process.env.ANTHROPIC_MODEL ?? "claude-haiku-5-5";
    this.apiKey = opts.apiKey ?? process.env.ANTHROPIC_API_KEY ?? "";
    this.baseUrl = (opts.baseUrl ?? process.env.ANTHROPIC_BASE_URL ?? "https://api.anthropic.com").replace(/\/$/, "");
    if (!this.apiKey) throw new Error("ANTHROPIC_API_KEY is not set");
    this.name = `anthropic (${this.model})`;
  }

  private call(body: Record<string, unknown>) {
    if (this.opts.temperature !== undefined) body.temperature = this.opts.temperature;
    return postJson(
      `${this.baseUrl}/v1/messages`,
      { "x-api-key": this.apiKey, "anthropic-version": "2023-06-01" },
      { model: this.model, ...body },
      { maxRetries: this.opts.maxRetries ?? 4, fetchImpl: this.opts.fetchImpl ?? fetch },
    );
  }

  async chooseTool({ prompt, tools }: ToolChoiceRequest): Promise<string | null> {
    const res = await this.call({
      max_tokens: 1024,
      system: ROUTER_SYSTEM,
      tool_choice: { type: "any" },
      tools: tools.map((t) => ({ name: t.id, description: t.description, input_schema: schemaFor(t) })),
      messages: [{ role: "user", content: prompt }],
    });
    const block = (res.content ?? []).find((c: { type: string }) => c.type === "tool_use");
    return block?.name ?? null;
  }

  async complete(system: string, user: string): Promise<string> {
    const res = await this.call({ max_tokens: 4096, system, messages: [{ role: "user", content: user }] });
    return (res.content ?? [])
      .filter((c: { type: string }) => c.type === "text")
      .map((c: { text: string }) => c.text)
      .join("");
  }
}

/** OpenAI, or anything that speaks the Chat Completions API: Ollama, vLLM, LM Studio, OpenRouter, Gemini's compat endpoint. */
export class OpenAICompatibleProvider implements Provider {
  readonly name: string;
  private readonly model: string;
  private readonly apiKey: string;
  private readonly baseUrl: string;
  private toolChoice: "required" | "auto" = "required";

  constructor(private readonly opts: ProviderOptions = {}) {
    this.model = opts.model ?? process.env.OPENAI_MODEL ?? "gpt-4.1-mini";
    this.apiKey = opts.apiKey ?? process.env.OPENAI_API_KEY ?? "";
    this.baseUrl = (opts.baseUrl ?? process.env.OPENAI_BASE_URL ?? "https://api.openai.com/v1").replace(/\/$/, "");
    if (!this.apiKey && this.baseUrl.includes("api.openai.com")) throw new Error("OPENAI_API_KEY is not set");
    this.name = `openai-compatible (${this.model} @ ${new URL(this.baseUrl).host})`;
  }

  private call(body: Record<string, unknown>) {
    if (this.opts.temperature !== undefined) body.temperature = this.opts.temperature;
    const headers: Record<string, string> = this.apiKey ? { authorization: `Bearer ${this.apiKey}` } : {};
    return postJson(
      `${this.baseUrl}/chat/completions`,
      headers,
      { model: this.model, ...body },
      { maxRetries: this.opts.maxRetries ?? 4, fetchImpl: this.opts.fetchImpl ?? fetch },
    );
  }

  async chooseTool({ prompt, tools }: ToolChoiceRequest): Promise<string | null> {
    const body = {
      messages: [
        { role: "system", content: ROUTER_SYSTEM },
        { role: "user", content: prompt },
      ],
      tools: tools.map((t) => ({
        type: "function",
        function: { name: t.id, description: t.description, parameters: schemaFor(t) },
      })),
    };
    let res;
    try {
      res = await this.call({ ...body, tool_choice: this.toolChoice });
    } catch (err) {
      // Some local servers reject tool_choice: "required". Fall back to "auto" once and remember.
      if (err instanceof HttpError && err.status === 400 && this.toolChoice === "required") {
        this.toolChoice = "auto";
        res = await this.call({ ...body, tool_choice: "auto" });
      } else throw err;
    }
    const call = res.choices?.[0]?.message?.tool_calls?.[0];
    return call?.function?.name ?? null;
  }

  async complete(system: string, user: string): Promise<string> {
    const res = await this.call({
      messages: [
        { role: "system", content: system },
        { role: "user", content: user },
      ],
    });
    return res.choices?.[0]?.message?.content ?? "";
  }
}

export type ProviderName = "anthropic" | "openai" | "offline";

export function createProvider(name: ProviderName, opts: ProviderOptions = {}): Provider {
  switch (name) {
    case "anthropic":
      return new AnthropicProvider(opts);
    case "openai":
      return new OpenAICompatibleProvider(opts);
    case "offline":
      return new OfflineProvider();
    default:
      throw new Error(`Unknown provider "${name}". Use anthropic, openai or offline.`);
  }
}

/** Picks a provider from whichever key is present, so `mcp-collide --config x.json` just works. */
export function detectProvider(): ProviderName {
  if (process.env.ANTHROPIC_API_KEY) return "anthropic";
  if (process.env.OPENAI_API_KEY || process.env.OPENAI_BASE_URL) return "openai";
  return "offline";
}
