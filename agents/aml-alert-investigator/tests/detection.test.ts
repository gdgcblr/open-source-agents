import {describe, expect, it} from 'vitest';
import {DEFAULT_RULES, type RuleConfig} from '../src/config.js';
import {DetectionEngine, runDetection} from '../src/detection.js';
import type {Transaction} from '../src/types.js';

// Ported 1:1 from DetectionEngineTest.java in the Sentinel AML project, plus engine-level tests.

function tx(id: string, type: 'CREDIT' | 'DEBIT', amount: number, jurisdiction: string, timestamp: string, extra: Partial<Transaction> = {}): Transaction {
  return {
    transactionId: id,
    accountId: 'ACC_TEST',
    customerId: 'CUST_TEST',
    type,
    amount,
    currency: 'INR',
    amountInr: amount,
    counterparty: 'Counterparty',
    channel: 'WIRE',
    jurisdiction,
    occurredAt: new Date(timestamp),
    ...extra,
  };
}

const engine = (rules: Partial<RuleConfig> = {}) => new DetectionEngine({...DEFAULT_RULES, ...rules});

describe('rules (parity with DetectionEngineTest.java)', () => {
  it('flags a reportable transaction', () => {
    expect(engine().threshold(tx('T1', 'CREDIT', 830_000, 'IN', '2026-09-19T10:00:00Z'))?.code).toBe('CTR_THRESHOLD');
  });

  it('flags three just-below-threshold transactions', () => {
    const first = tx('T1', 'CREDIT', 800_000, 'IN', '2026-09-19T08:00:00Z');
    const second = tx('T2', 'CREDIT', 800_000, 'IN', '2026-09-19T09:00:00Z');
    const third = tx('T3', 'CREDIT', 800_000, 'IN', '2026-09-19T10:00:00Z');
    expect(engine().structuring(third, [first, second, third])?.code).toBe('STRUCTURING');
  });

  it('flags rapid movement of a deposit', () => {
    const deposit = tx('T1', 'CREDIT', 1_000_000, 'IN', '2026-09-18T10:00:00Z');
    const w1 = tx('T2', 'DEBIT', 400_000, 'AE', '2026-09-19T09:00:00Z');
    const w2 = tx('T3', 'DEBIT', 400_000, 'AE', '2026-09-19T10:00:00Z');
    expect(engine().rapidMovement(w2, [deposit, w1, w2])?.code).toBe('RAPID_MOVEMENT');
  });

  it('flags a high-risk jurisdiction regardless of amount', () => {
    expect(engine().highRisk(tx('T1', 'DEBIT', 1, 'IR', '2026-09-19T10:00:00Z'))?.score).toBe(95);
  });

  it('flags a configured high-risk counterparty', () => {
    const t = tx('T1', 'DEBIT', 1, 'IN', '2026-09-19T10:00:00Z', {counterparty: 'Blocked Entity'});
    expect(engine({highRiskCounterparties: ['blocked entity']}).highRisk(t)).not.toBeNull();
  });

  it('does not match a disabled rule', () => {
    expect(engine({thresholdEnabled: false}).threshold(tx('T1', 'CREDIT', 900_000, 'IN', '2026-09-19T10:00:00Z'))).toBeNull();
  });

  it('flags behaviour above three times the 90-day average', () => {
    const e = engine();
    e.evaluate(tx('T1', 'CREDIT', 90_000, 'IN', '2026-09-01T10:00:00Z'));
    e.evaluate(tx('T2', 'CREDIT', 4_000, 'IN', '2026-09-19T10:00:00Z'));
    expect(e.behavioralDeviation(tx('T2', 'CREDIT', 4_000, 'IN', '2026-09-19T10:00:00Z'))?.code).toBe('BEHAVIORAL_DEVIATION');
  });

  it('flags repeated round-number transactions', () => {
    const first = tx('T1', 'CREDIT', 100_000, 'IN', '2026-09-19T09:00:00Z');
    const second = tx('T2', 'CREDIT', 200_000, 'IN', '2026-09-19T10:00:00Z');
    expect(engine().roundNumber(second, [first, second])?.code).toBe('ROUND_NUMBER');
  });
});

describe('engine', () => {
  it('does not flag rapid movement below the 80% ratio', () => {
    const deposit = tx('T1', 'CREDIT', 1_000_000, 'IN', '2026-09-18T10:00:00Z');
    const out = tx('T2', 'DEBIT', 790_000, 'IN', '2026-09-19T10:00:00Z');
    expect(engine().rapidMovement(out, [deposit, out])).toBeNull();
  });

  it('scores max rule + 5 per extra rule, capped at 100', () => {
    const e = engine();
    const alert = e.evaluate(tx('T1', 'DEBIT', 900_000, 'IR', '2026-09-19T10:00:00Z'));
    // HIGH_RISK (95) + CTR (70) -> 95 + 5.
    expect(alert?.ruleCodes).toEqual(['CTR_THRESHOLD', 'HIGH_RISK_JURISDICTION']);
    expect(alert?.riskScore).toBe(100);
  });

  it('aggregates the same pattern on the same account and day into one alert', () => {
    const run = runDetection(
      [tx('T1', 'DEBIT', 10, 'IR', '2026-09-19T08:00:00Z'), tx('T2', 'DEBIT', 20, 'IR', '2026-09-19T09:00:00Z')],
      {...DEFAULT_RULES, behavioralDeviationEnabled: false},
    );
    expect(run.alerts).toHaveLength(1);
    expect(run.alerts[0].evidenceIds).toEqual(['T1', 'T2']);
  });

  it('evaluates in time order regardless of input order', () => {
    const a = tx('T1', 'CREDIT', 800_000, 'IN', '2026-09-19T08:00:00Z');
    const b = tx('T2', 'CREDIT', 800_000, 'IN', '2026-09-19T09:00:00Z');
    const c = tx('T3', 'CREDIT', 800_000, 'IN', '2026-09-19T10:00:00Z');
    const forward = runDetection([a, b, c], DEFAULT_RULES).alerts.map((x) => x.ruleCodes.join());
    const shuffled = runDetection([c, a, b], DEFAULT_RULES).alerts.map((x) => x.ruleCodes.join());
    expect(shuffled).toEqual(forward);
  });

  it('processes 10,000 transactions well under the 2-minute target', () => {
    const start = Date.parse('2026-06-01T00:00:00Z');
    const txns = Array.from({length: 10_000}, (_, i) =>
      tx(`T${i}`, i % 3 === 0 ? 'DEBIT' : 'CREDIT', 1_000 + ((i * 7919) % 900_000), i % 97 === 0 ? 'IR' : 'IN',
        new Date(start + i * 600_000).toISOString(), {accountId: `ACC_${i % 100}`, customerId: `CUST_${i % 50}`}),
    );
    const run = runDetection(txns, DEFAULT_RULES);
    expect(run.transactionsEvaluated).toBe(10_000);
    expect(run.elapsedMs).toBeLessThan(10_000);
  });
});
