import {mkdtempSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {describe, expect, it} from 'vitest';
import {DEFAULT_RULES, loadRuleConfig} from '../src/config.js';
import {loadDataset, parseCsv} from '../src/csv.js';
import {fallbackInvestigation} from '../src/fallback.js';
import {guardInvestigation} from '../src/guardrails.js';
import {alertCase, alertQueue, buildWorkspace, recommendationFloor} from '../src/investigation.js';
import {maskName, scrubCustomerPii} from '../src/pii.js';

const ws = buildWorkspace('data', DEFAULT_RULES);
const customers = () => ws.dataset.customers.values();
const top = alertCase(ws, 'ALT-0006')!;

describe('ingestion', () => {
  it('parses quoted fields with commas, quotes and newlines', () => {
    expect(parseCsv('a,b\n"x, y","say ""hi""\nthere"\n')).toEqual([{a: 'x, y', b: 'say "hi"\nthere'}]);
  });

  it('loads the Sentinel sample data without errors', () => {
    expect(ws.dataset.errors).toEqual([]);
    expect([ws.dataset.customers.size, ws.dataset.accounts.size, ws.dataset.transactions.length]).toEqual([2, 2, 7]);
  });

  it('rejects malformed rows and unknown references, and skips duplicates', () => {
    const dir = mkdtempSync(join(tmpdir(), 'aml-'));
    writeFileSync(join(dir, 'customers.csv'), 'customer_id,first_name,last_name,date_of_birth,country,risk_rating\nC_001,A,B,1990-01-01,IN,LOW\n');
    writeFileSync(join(dir, 'accounts.csv'), 'account_id,customer_id,account_type,account_status,currency,open_date\nA_001,C_001,SAVINGS,ACTIVE,INR,2020-01-01\nA_002,C_999,SAVINGS,ACTIVE,INR,2020-01-01\n');
    writeFileSync(
      join(dir, 'transactions.csv'),
      'transaction_id,account_id,transaction_type,amount,currency,counterparty,channel,timestamp,jurisdiction\n' +
        'T_001,A_001,CREDIT,100,INR,X,UPI,2026-09-18T09:00:00Z,IN\n' +
        'T_001,A_001,CREDIT,100,INR,X,UPI,2026-09-18T09:00:00Z,IN\n' +
        'T_002,A_404,CREDIT,100,INR,X,UPI,2026-09-18T09:00:00Z,IN\n' +
        'T_003,A_001,REFUND,100,INR,X,UPI,2026-09-18T09:00:00Z,IN\n' +
        'T_004,A_001,CREDIT,-5,INR,X,UPI,2026-09-18T09:00:00Z,IN\n' +
        'T_005,A_001,CREDIT,100,JPY,X,UPI,2026-09-18T09:00:00Z,IN\n' +
        'T_006,A_001,CREDIT,100,INR,X,UPI,yesterday,IN\n',
    );
    const d = loadDataset(dir, DEFAULT_RULES);
    expect(d.transactions.map((t) => t.transactionId)).toEqual(['T_001']);
    expect(d.duplicatesSkipped).toBe(1);
    expect(d.errors).toEqual([
      'accounts.csv row 3: unknown customer_id C_999',
      'transactions.csv row 4: unknown account_id A_404',
      'transactions.csv row 5: transaction_type must be CREDIT or DEBIT',
      'transactions.csv row 6: amount must be a positive number',
      'transactions.csv row 7: no INR exchange rate configured for JPY',
      'transactions.csv row 8: timestamp must be ISO-8601, e.g. 2026-09-18T09:00:00Z',
    ]);
  });

  it('normalises foreign currency to INR', () => {
    const dir = mkdtempSync(join(tmpdir(), 'aml-'));
    writeFileSync(join(dir, 'customers.csv'), 'customer_id,first_name,last_name,date_of_birth,country,risk_rating\nC_001,A,B,1990-01-01,IN,LOW\n');
    writeFileSync(join(dir, 'accounts.csv'), 'account_id,customer_id,account_type,account_status,currency,open_date\nA_001,C_001,NRE,ACTIVE,USD,2020-01-01\n');
    writeFileSync(join(dir, 'transactions.csv'), 'transaction_id,account_id,transaction_type,amount,currency,counterparty,channel,timestamp,jurisdiction\nT_1,A_001,CREDIT,10000,USD,X,WIRE,2026-09-18T09:00:00Z,US\n');
    expect(loadDataset(dir, DEFAULT_RULES).transactions[0].amountInr).toBe(830_000);
  });

  it('rejects invalid rule files', () => {
    const file = join(mkdtempSync(join(tmpdir(), 'aml-')), 'rules.json');
    writeFileSync(file, JSON.stringify({structuringCount: 4, highRiskJurisdictions: ['IR', 'MM']}));
    expect(loadRuleConfig(file)).toMatchObject({structuringCount: 4, highRiskJurisdictions: ['IR', 'MM'], reportThresholdInr: 830_000});
    writeFileSync(file, JSON.stringify({structuringCount: 'three'}));
    expect(() => loadRuleConfig(file)).toThrow();
    writeFileSync(file, JSON.stringify({typo: true}));
    expect(() => loadRuleConfig(file)).toThrow();
  });
});

describe('sample data (all six typologies)', () => {
  it('produces the expected risk-sorted alert queue', () => {
    expect(alertQueue(ws).map((a) => [a.alertId, a.riskScore, a.ruleCodes.join(',')])).toEqual([
      ['ALT-0005', 100, 'BEHAVIORAL_DEVIATION,CTR_THRESHOLD,ROUND_NUMBER,STRUCTURING'],
      ['ALT-0006', 100, 'BEHAVIORAL_DEVIATION,HIGH_RISK_JURISDICTION,RAPID_MOVEMENT'],
      ['ALT-0003', 95, 'ROUND_NUMBER,STRUCTURING'],
      ['ALT-0004', 95, 'BEHAVIORAL_DEVIATION,CTR_THRESHOLD,RAPID_MOVEMENT'],
      ['ALT-0001', 70, 'CTR_THRESHOLD'],
      ['ALT-0002', 45, 'ROUND_NUMBER'],
    ]);
  });

  it('never exposes direct identifiers in the queue or case file', () => {
    const json = JSON.stringify([alertQueue(ws), ...ws.run.alerts.map((a) => alertCase(ws, a.alertId))]);
    for (const c of customers()) {
      for (const value of [c.firstName, c.lastName, c.email, c.phone, c.dateOfBirth]) expect(json).not.toContain(value);
    }
  });
});

describe('recommendation floor', () => {
  it('requires escalation for sanctions hits and very high scores', () => {
    expect(recommendationFloor({riskScore: 50, ruleCodes: ['HIGH_RISK_JURISDICTION']})).toBe('ESCALATE');
    expect(recommendationFloor({riskScore: 90, ruleCodes: ['STRUCTURING']})).toBe('ESCALATE');
    expect(recommendationFloor({riskScore: 70, ruleCodes: ['CTR_THRESHOLD']})).toBe('INVESTIGATE');
    expect(recommendationFloor({riskScore: 45, ruleCodes: ['ROUND_NUMBER']})).toBe('CLOSE_FALSE_POSITIVE');
  });
});

describe('output guardrails', () => {
  const good = 'RECOMMENDATION: ESCALATE\n**Summary** TXN_000005 then TXN_000006 to AE.\n**Draft SAR narrative**: DRAFT for analyst review. Not filed.';

  it('accepts a grounded answer', () => {
    const g = guardInvestigation(good, top, customers());
    expect(g.rejected).toBeUndefined();
    expect(g.recommendation).toBe('ESCALATE');
  });

  it('rejects a recommendation below the floor', () => {
    expect(guardInvestigation('RECOMMENDATION: CLOSE_FALSE_POSITIVE\nLooks fine. DRAFT', top, customers()).rejected).toMatch(/below the required minimum/);
  });

  it('rejects invented transaction IDs', () => {
    expect(guardInvestigation(`${good}\nAlso TXN_999999.`, top, customers()).rejected).toMatch(/TXN_999999/);
  });

  it('rejects claims that a report was filed', () => {
    expect(guardInvestigation(`${good}\nThe SAR has been filed with FIU-IND.`, top, customers()).rejected).toMatch(/only draft/);
  });

  it('rejects answers without the required narrative (seen live: "0.25")', () => {
    expect(guardInvestigation('0.25', top, customers()).rejected).toMatch(/missing the required draft/);
  });

  it('removes leaked identifiers and adds a missing DRAFT label', () => {
    const g = guardInvestigation('RECOMMENDATION: ESCALATE\nKrishna Sharma moved funds (TXN_000006).\nDraft SAR narrative: see above.', top, customers());
    expect(g.text).not.toContain('Krishna');
    expect(g.text).toMatch(/^> DRAFT/);
    expect(g.corrections).toHaveLength(2);
  });

  it('falls back to the floor when the RECOMMENDATION line is missing', () => {
    const g = guardInvestigation('Summary only.\nDraft SAR narrative: DRAFT', top, customers());
    expect(g.recommendation).toBe('ESCALATE');
    expect(g.corrections[0]).toMatch(/skipped the RECOMMENDATION line/);
  });
});

describe('fallback', () => {
  it('only cites evidence from the case file and passes its own guardrails', () => {
    const text = fallbackInvestigation(top, 'test');
    for (const t of top.evidence) expect(text).toContain(t.transactionId);
    expect(guardInvestigation(`RECOMMENDATION: ESCALATE\n${text}`, top, customers()).rejected).toBeUndefined();
  });
});

describe('pii helpers', () => {
  it('masks names and scrubs identifiers', () => {
    expect(maskName({firstName: 'Anika', lastName: 'Fernandes'})).toBe('A**** F********');
    const c = [...customers()][0];
    expect(scrubCustomerPii(`Contact ${c.email} or ${c.phone}`, customers())).toBe('Contact [REDACTED] or [REDACTED]');
  });
});
