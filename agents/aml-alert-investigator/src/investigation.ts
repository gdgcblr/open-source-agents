import {type RuleConfig} from './config.js';
import {loadDataset} from './csv.js';
import {type DetectionRun, runDetection} from './detection.js';
import {maskName} from './pii.js';
import type {Alert, Dataset, Transaction} from './types.js';

export type Recommendation = 'CLOSE_FALSE_POSITIVE' | 'INVESTIGATE' | 'ESCALATE';
export const RECOMMENDATION_RANK: Record<Recommendation, number> = {CLOSE_FALSE_POSITIVE: 0, INVESTIGATE: 1, ESCALATE: 2};

export interface Workspace {
  dataset: Dataset;
  run: DetectionRun;
  rules: RuleConfig;
}

export function buildWorkspace(dataDir: string, rules: RuleConfig): Workspace {
  const dataset = loadDataset(dataDir, rules);
  return {dataset, run: runDetection(dataset.transactions, rules), rules};
}

/**
 * The least severe outcome an alert may receive. The agent can recommend something stricter, never weaker.
 * Sanctions/high-risk hits always escalate (business rule 4); high scores need a human investigation at minimum.
 */
export function recommendationFloor(alert: Pick<Alert, 'riskScore' | 'ruleCodes'>): Recommendation {
  if (alert.ruleCodes.includes('HIGH_RISK_JURISDICTION') || alert.riskScore >= 90) return 'ESCALATE';
  if (alert.riskScore >= 70) return 'INVESTIGATE';
  return 'CLOSE_FALSE_POSITIVE';
}

function riskBand(score: number): string {
  if (score >= 90) return '90-100';
  if (score >= 70) return '70-89';
  if (score >= 40) return '40-69';
  return '0-39';
}

const inr = (n: number) => Math.round(n * 100) / 100;

/** List view: PII masked, sorted by risk. */
export function alertQueue(ws: Workspace) {
  return ws.run.alerts.map((a) => {
    const customer = ws.dataset.customers.get(a.customerId);
    return {
      alertId: a.alertId,
      riskScore: a.riskScore,
      riskBand: riskBand(a.riskScore),
      ruleCodes: a.ruleCodes,
      accountId: a.accountId,
      customerId: a.customerId,
      customerName: customer ? maskName(customer) : 'unknown',
      evidenceCount: a.evidenceIds.length,
      status: a.status,
    };
  });
}

function txView(t: Transaction) {
  return {
    transactionId: t.transactionId,
    occurredAt: t.occurredAt.toISOString(),
    type: t.type,
    amount: t.amount,
    currency: t.currency,
    amountInr: inr(t.amountInr),
    counterparty: t.counterparty,
    channel: t.channel,
    jurisdiction: t.jurisdiction,
  };
}

export type CaseFile = NonNullable<ReturnType<typeof alertCase>>;

/**
 * Everything an investigator needs for one alert, with direct identifiers (full name, email, phone,
 * date of birth) removed so they are never sent to the model.
 */
export function alertCase(ws: Workspace, alertId: string) {
  const alert = ws.run.alerts.find((a) => a.alertId === alertId);
  if (!alert) return null;
  const customer = ws.dataset.customers.get(alert.customerId);
  const account = ws.dataset.accounts.get(alert.accountId);
  const timeline = ws.dataset.transactions
    .filter((t) => t.accountId === alert.accountId)
    .sort((a, b) => a.occurredAt.getTime() - b.occurredAt.getTime());
  const evidence = timeline.filter((t) => alert.evidenceIds.includes(t.transactionId));
  const total = (list: Transaction[], type?: string) => inr(list.filter((t) => !type || t.type === type).reduce((s, t) => s + t.amountInr, 0));

  return {
    alert: {
      alertId: alert.alertId,
      riskScore: alert.riskScore,
      ruleCodes: alert.ruleCodes,
      explanation: alert.explanation,
      status: alert.status,
      minimumRecommendation: recommendationFloor(alert),
    },
    customer: customer && {
      customerId: customer.customerId,
      maskedName: maskName(customer),
      country: customer.country,
      occupation: customer.occupation || 'not provided',
      declaredAnnualIncomeInr: customer.annualIncome,
      segment: customer.segment,
      kycStatus: customer.kycStatus,
      riskRating: customer.riskRating,
      politicallyExposed: customer.politicallyExposed,
      customerSince: customer.customerSince,
      otherAccountIds: [...ws.dataset.accounts.values()]
        .filter((a) => a.customerId === customer.customerId && a.accountId !== alert.accountId)
        .map((a) => a.accountId),
    },
    account: account && {
      accountId: account.accountId,
      accountType: account.accountType,
      status: account.status,
      currency: account.currency,
      openDate: account.openDate,
      branchCity: account.branchCity,
      avgMonthlyBalance6mInr: account.avgMonthlyBalance6m,
      avgMonthlyTxnCount: account.avgMonthlyTxnCount,
    },
    evidence: evidence.map(txView),
    timeline: timeline.map(txView),
    totals: {
      evidenceInr: total(evidence),
      creditsInr: total(timeline, 'CREDIT'),
      debitsInr: total(timeline, 'DEBIT'),
      jurisdictions: [...new Set(timeline.map((t) => t.jurisdiction))],
    },
  };
}
