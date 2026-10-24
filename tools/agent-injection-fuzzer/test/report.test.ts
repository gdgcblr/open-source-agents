import { test } from 'node:test';
import assert from 'node:assert/strict';
import { renderTable, summarize, type Report } from '../src/report.js';
import type { CaseResult, Outcome } from '../src/types.js';

function result(outcome: Outcome, id: string = outcome.toLowerCase()): CaseResult {
  return {
    payload: { id, family: 'test', text: '' },
    locked: false,
    outcome,
    trace: { delivered: true, executedTools: [], blockedTools: [], agentText: '' },
    sent: [],
  };
}

test('void cases are counted apart from breaches and holds', () => {
  const report: Report = {
    model: 'test',
    generatedAt: '',
    baseline: (['UNAUTHORIZED_CALL', 'LEAK', 'ERROR', 'NO_DELIVERY', 'PASS'] as const).map((outcome) => result(outcome)),
    hardened: (['BLOCKED', 'PASS'] as const).map((outcome) => result(outcome)),
  };
  const text = summarize(report);
  assert.match(text, /lock off: 2 breached, 1 held, 2 void \(of 5\)/);
  assert.match(text, /lock on: {2}0 breached, 2 held, 0 void \(of 2\)/);
});

test('with several trials a cell shows the worst outcome and the breach count', () => {
  const report: Report = {
    model: 'test',
    generatedAt: '',
    baseline: [result('PASS', 'p'), result('ERROR', 'p'), result('UNAUTHORIZED_CALL', 'p')],
    hardened: [result('ERROR', 'p'), result('ERROR', 'p'), result('BLOCKED', 'p')],
  };
  const row = renderTable(report).split('\n').find((line) => line.trimStart().startsWith('p '));
  assert.ok(row, 'the payload has a row');
  assert.match(row, /UNAUTHORIZED_CALL 1\/3\s+BLOCKED 0\/3$/);
});
