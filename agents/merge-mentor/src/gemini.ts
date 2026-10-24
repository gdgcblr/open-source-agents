import { ApiError, GoogleGenAI, type GenerateContentConfig, type GenerateContentParameters, type GenerateContentResponse } from '@google/genai';

const REQUEST_TIMEOUT_MS = 45_000;
const COOLDOWN_MS = 10 * 60_000;
/** Hard stop for runaway loops: one process may make at most this many model calls. */
const MAX_CALLS = 120;

/** Lighter models tried in order when the preferred one is rate-limited or unavailable. */
export const FALLBACK_MODELS = ['gemini-3.5-flash-lite', 'gemini-3.1-flash-lite'];

export class Gemini {
  private readonly ai: GoogleGenAI;
  private readonly models: string[];
  /** Models that just failed (quota, overload, timeout) are skipped for a while, then retried. */
  private readonly deadUntil = new Map<string, number>();

  constructor(apiKey: string, preferredModel: string) {
    // One attempt per model: the SDK's default retries can stall for minutes on a daily-quota 429.
    this.ai = new GoogleGenAI({ apiKey, httpOptions: { timeout: REQUEST_TIMEOUT_MS, retryOptions: { attempts: 1 } } });
    this.models = [preferredModel, ...FALLBACK_MODELS.filter((m) => m !== preferredModel)];
  }

  private calls = 0;

  async generate(params: Omit<GenerateContentParameters, 'model'> & { config?: GenerateContentConfig }): Promise<GenerateContentResponse> {
    if (++this.calls > MAX_CALLS) throw new Error(`Gemini call budget reached (${MAX_CALLS} per run). Restart merge-mentor to continue.`);
    let lastError: unknown;
    for (const model of this.models) {
      if ((this.deadUntil.get(model) ?? 0) > Date.now()) continue;
      try {
        return await this.ai.models.generateContent({ ...params, model });
      } catch (error) {
        lastError = error;
        const status = error instanceof ApiError ? error.status : 0;
        // Quota, overload, unknown model, or timeout: try the next model. Anything else is a real error.
        const retryable = [404, 429, 500, 503, 504].includes(status) || (error as Error).name === 'AbortError' || /timed? ?out|aborted/i.test((error as Error).message);
        if (!retryable) throw error;
        this.deadUntil.set(model, Date.now() + COOLDOWN_MS);
      }
    }
    throw new Error(`Gemini is unavailable (${(lastError as Error)?.message?.slice(0, 160) ?? 'unknown error'}). Check your quota at https://ai.google.dev/gemini-api/docs/rate-limits`);
  }
}
