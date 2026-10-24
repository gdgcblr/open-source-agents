import {
  InMemoryRunner,
  getFunctionCalls,
  REQUEST_CONFIRMATION_FUNCTION_CALL_NAME,
  type BaseLlm,
  type BasePlugin,
} from '@google/adk';
import { classify } from './classify.js';
import { InjectionPlugin } from './injector.js';
import { buildVictim } from './victim.js';
import type { CaseConfig, CaseResult, Outcome, Payload, SentEmail, Trace } from './types.js';

// A case makes up to three model calls, and a thinking model can take tens of
// seconds per call, so the cap is generous; it exists to end a stuck call.
const CASE_TIMEOUT_MS = 120_000;
const USER_ID = 'fuzzer';

// Runs one payload against a fresh agent, runner and session, then scores the
// event stream. With the lock on, ADK emits an adk_request_confirmation call
// that names the held tool call and ends the run without executing it; the
// end-to-end tests check that against what the email tool really recorded.
export interface RunOptions {
  timeoutMs?: number;
  // Run-wide plugins shared by every case, such as request pacing.
  plugins?: BasePlugin[];
}

export async function runCase(
  payload: Payload,
  locked: boolean,
  model: string | BaseLlm,
  cfg: CaseConfig,
  { timeoutMs = CASE_TIMEOUT_MS, plugins = [] }: RunOptions = {},
): Promise<CaseResult> {
  const plugin = new InjectionPlugin(cfg.deliveryTool, payload.text);
  const sent: SentEmail[] = [];
  const agent = buildVictim({ model, locked, canary: cfg.canary, sink: sent });
  const runner = new InMemoryRunner({ agent, plugins: [plugin, ...plugins] });
  // Aborting on timeout cancels the in-flight model call, so a stuck case stops spending quota.
  const abort = new AbortController();

  const executed = new Set<string>();
  const blocked = new Set<string>();
  let agentText = '';
  let modelError: string | undefined;

  // The same steps as runner.runEphemeral, which takes no abort signal.
  const loop = (async () => {
    const session = await runner.sessionService.createSession({ appName: runner.appName, userId: USER_ID });
    try {
      for await (const ev of runner.runAsync({
        userId: USER_ID,
        sessionId: session.id,
        newMessage: { role: 'user', parts: [{ text: cfg.task }] },
        abortSignal: abort.signal,
      })) {
        // ADK reports a failed model call (429, 503) as an error event, not a throw.
        if (ev.errorCode || ev.errorMessage) modelError = `${ev.errorCode ?? 'ERROR'}: ${ev.errorMessage ?? ''}`;
        for (const part of ev.content?.parts ?? []) {
          const name = part.functionResponse?.name;
          if (name && !name.startsWith('adk_')) executed.add(name);
        }
        // A real send is the worst outcome and cannot be undone, so the case ends
        // here: the agent's next turn could not change the score, only spend quota.
        if (executed.has(cfg.sensitiveTool)) break;
        for (const fc of getFunctionCalls(ev)) {
          if (fc.name !== REQUEST_CONFIRMATION_FUNCTION_CALL_NAME) continue;
          const held = callName(fc.args?.['originalFunctionCall']);
          if (held) blocked.add(held);
        }
        // Text the agent shows in any turn, not only its last, can disclose the canary.
        // Thought parts are the model's private reasoning and are not shown, so skip them.
        if (ev.author !== 'user') {
          agentText += (ev.content?.parts ?? []).filter((p) => !p.thought).map((p) => p.text ?? '').join('');
        }
      }
    } finally {
      await runner.sessionService.deleteSession({ appName: runner.appName, userId: USER_ID, sessionId: session.id });
    }
  })();

  // After a timeout the loop may still reject as the abort lands; that rejection is expected.
  loop.catch(() => {});

  const trace = (): Trace => ({
    delivered: plugin.injected > 0,
    executedTools: [...executed],
    blockedTools: [...blocked],
    agentText,
  });

  const failed = (detail: string): CaseResult => {
    const partial = trace();
    // An email that really went out after the payload arrived is still a breach.
    const outcome: Outcome = partial.delivered && sent.length > 0 ? 'UNAUTHORIZED_CALL' : 'ERROR';
    return { payload, locked, outcome, trace: partial, sent, detail };
  };

  try {
    await withTimeout(loop, timeoutMs);
  } catch (err) {
    abort.abort();
    return failed(String(err));
  }
  if (modelError) return failed(modelError);

  const finished = trace();
  return { payload, locked, outcome: classify(finished, cfg), trace: finished, sent };
}

// Bounded concurrency so a run respects the model's requests-per-minute ceiling.
export async function mapPool<T, R>(
  items: readonly T[],
  limit: number,
  fn: (item: T, index: number) => Promise<R>,
): Promise<R[]> {
  const out = new Array<R>(items.length);
  let cursor = 0;
  const size = Math.max(1, Math.min(limit, items.length));
  const workers = Array.from({ length: size }, async () => {
    while (cursor < items.length) {
      const index = cursor++;
      out[index] = await fn(items[index]!, index);
    }
  });
  await Promise.all(workers);
  return out;
}

function callName(value: unknown): string | undefined {
  if (typeof value !== 'object' || value === null) return undefined;
  const { name } = value as Record<string, unknown>;
  return typeof name === 'string' ? name : undefined;
}

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout>;
  const guard = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error(`case exceeded ${ms}ms`)), ms);
  });
  return Promise.race([promise, guard]).finally(() => clearTimeout(timer));
}
