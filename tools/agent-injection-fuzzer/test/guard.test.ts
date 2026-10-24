import { test } from 'node:test';
import assert from 'node:assert/strict';
import { guardRuns } from '../src/guard.js';
import type { CaseResult, Outcome, Payload } from '../src/types.js';

const PAYLOAD: Payload = { id: 'p', family: 'test', text: '' };
const NO_WAIT = [0, 0];
const BUSY = '503: This model is currently experiencing high demand.';
const DAILY = '429: Generate content requests per day limit exceeded on Free Tier.';

function result(outcome: Outcome, detail?: string): CaseResult {
  const trace = { delivered: true, executedTools: [], blockedTools: [], agentText: '' };
  return { payload: PAYLOAD, locked: false, outcome, trace, sent: [], ...(detail ? { detail } : {}) };
}

// A fake model run that replays the given results in order and counts its calls.
function scripted(...results: CaseResult[]) {
  let calls = 0;
  const runOnce = async () => results[Math.min(calls++, results.length - 1)]!;
  return { runOnce, calls: () => calls };
}

test('a busy model is retried and a later success is kept', async () => {
  const fake = scripted(result('ERROR', BUSY), result('PASS'));
  const guard = guardRuns(fake.runOnce, NO_WAIT);
  const r = await guard.run(PAYLOAD, false);
  assert.equal(r.outcome, 'PASS');
  assert.equal(guard.retries(), 1);
  assert.equal(guard.stopReason(), undefined);
});

test('two cases that stay busy stop the run before a third model call', async () => {
  const fake = scripted(result('ERROR', BUSY));
  const guard = guardRuns(fake.runOnce, NO_WAIT);
  await guard.run(PAYLOAD, false);
  await guard.run(PAYLOAD, true);
  const callsBefore = fake.calls();
  const third = await guard.run(PAYLOAD, false);
  assert.equal(fake.calls(), callsBefore, 'the third case never called the model');
  assert.match(third.detail ?? '', /not run: the model kept failing/);
});

test('a per-day quota stops at once without retries', async () => {
  const fake = scripted(result('ERROR', DAILY));
  const guard = guardRuns(fake.runOnce, NO_WAIT);
  await guard.run(PAYLOAD, false);
  assert.equal(fake.calls(), 1);
  assert.equal(guard.retries(), 0);
  assert.match(guard.stopReason() ?? '', /daily quota/);
});

test('a 500 internal error from the model API is retried', async () => {
  const fake = scripted(result('ERROR', '500: Internal error encountered.'), result('PASS'));
  const guard = guardRuns(fake.runOnce, NO_WAIT);
  const r = await guard.run(PAYLOAD, false);
  assert.equal(r.outcome, 'PASS');
  assert.equal(guard.retries(), 1);
});

test('a non-transient error is not retried', async () => {
  const fake = scripted(result('ERROR', 'API key not valid'));
  const guard = guardRuns(fake.runOnce, NO_WAIT);
  const r = await guard.run(PAYLOAD, false);
  assert.equal(r.outcome, 'ERROR');
  assert.equal(fake.calls(), 1);
});
