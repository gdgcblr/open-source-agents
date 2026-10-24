import { setTimeout as sleep } from 'node:timers/promises';
import type { CaseResult, Payload } from './types.js';

// Protects a small model quota. A busy or rate-limited model gets a couple of
// spaced retries; a per-day quota, or two cases in a row that still fail after
// their retries, stops the run from calling the model at all. A live run on the
// free tier showed why: a 503 "high demand" model plus blind retries spent the
// whole 20-request daily quota without producing one answer.

// Per-minute limits clear within a minute, so the waits span most of one window.
export const RETRY_DELAYS_MS: readonly number[] = [10_000, 30_000];
// The status codes match the ones @google/genai itself treats as retryable.
const TRANSIENT =
  /\b(408|429|500|502|503|504)\b|RESOURCE_EXHAUSTED|UNAVAILABLE|INTERNAL|overloaded|high demand|rate limit|quota|case exceeded/i;
const DAILY_QUOTA = /per day|PerDay/i;
const FAILED_CASES_BEFORE_STOP = 2;

export interface GuardedRunner {
  run(payload: Payload, locked: boolean): Promise<CaseResult>;
  retries(): number;
  stopReason(): string | undefined;
}

export function guardRuns(
  runOnce: (payload: Payload, locked: boolean) => Promise<CaseResult>,
  delays: readonly number[] = RETRY_DELAYS_MS,
): GuardedRunner {
  let retries = 0;
  let failedInARow = 0;
  let stopReason: string | undefined;

  const transient = (r: CaseResult) => r.outcome === 'ERROR' && TRANSIENT.test(r.detail ?? '');

  const run = async (payload: Payload, locked: boolean): Promise<CaseResult> => {
    if (stopReason) return notRun(payload, locked, `not run: ${stopReason}`);
    let result = await runOnce(payload, locked);
    for (const delay of delays) {
      if (!transient(result)) break;
      if (DAILY_QUOTA.test(result.detail ?? '')) {
        stopReason = 'the model daily quota is used up';
        return result;
      }
      retries += 1;
      await sleep(delay);
      result = await runOnce(payload, locked);
    }
    failedInARow = transient(result) ? failedInARow + 1 : 0;
    if (failedInARow >= FAILED_CASES_BEFORE_STOP) {
      stopReason = 'the model kept failing as busy or rate-limited; try again later';
    }
    return result;
  };

  return { run, retries: () => retries, stopReason: () => stopReason };
}

function notRun(payload: Payload, locked: boolean, detail: string): CaseResult {
  const trace = { delivered: false, executedTools: [], blockedTools: [], agentText: '' };
  return { payload, locked, outcome: 'ERROR', trace, sent: [], detail };
}
