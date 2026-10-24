import type {RuleConfig} from './config.js';
import type {Alert, RuleCode, RuleMatch, Transaction} from './types.js';

const HOUR_MS = 3_600_000;
const DAY_MS = 86_400_000;
const AGGREGATION_BONUS = 5;

function utcDay(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function startOfUtcDay(date: Date): number {
  return Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
}

function sum(list: Transaction[]): number {
  return list.reduce((total, t) => total + t.amountInr, 0);
}

/**
 * TypeScript port of DetectionEngine.java from the Sentinel AML project.
 * Rule codes, scores, thresholds and explanations are kept identical so results match the original.
 */
export class DetectionEngine {
  private readonly byAccount = new Map<string, Transaction[]>();
  private readonly byCustomer = new Map<string, Transaction[]>();
  private readonly alerts = new Map<string, Alert>();

  constructor(private readonly rules: RuleConfig) {}

  /** Records the transaction, then evaluates every rule against it (the original saves before evaluating). */
  evaluate(transaction: Transaction): Alert | null {
    this.record(transaction);
    const windowHours = Math.max(24, this.rules.structuringWindowHours, this.rules.rapidMovementHours);
    const history = this.accountHistory(transaction, windowHours);

    const matches = [
      this.threshold(transaction),
      this.structuring(transaction, history),
      this.rapidMovement(transaction, history),
      this.highRisk(transaction),
      this.behavioralDeviation(transaction),
      this.roundNumber(transaction, history),
    ].filter((m): m is RuleMatch => m !== null);
    if (matches.length === 0) return null;

    const ruleCodes = matches.map((m) => m.code).sort() as RuleCode[];
    const riskScore = Math.min(100, Math.max(...matches.map((m) => m.score)) + (matches.length - 1) * AGGREGATION_BONUS);
    const explanation = matches.map((m) => m.explanation).join(' ');
    const dedupeKey = `${transaction.accountId}:${ruleCodes.join(',')}:${utcDay(transaction.occurredAt)}`;

    let alert = this.alerts.get(dedupeKey);
    if (!alert) {
      alert = {
        alertId: `ALT-${String(this.alerts.size + 1).padStart(4, '0')}`,
        dedupeKey,
        customerId: transaction.customerId,
        accountId: transaction.accountId,
        ruleCodes,
        riskScore,
        explanation,
        evidenceIds: [],
        status: 'OPEN',
      };
      this.alerts.set(dedupeKey, alert);
    }
    alert.riskScore = Math.max(alert.riskScore, riskScore);
    alert.explanation = explanation;
    for (const t of matches.flatMap((m) => m.evidence)) {
      if (!alert.evidenceIds.includes(t.transactionId)) alert.evidenceIds.push(t.transactionId);
    }
    return alert;
  }

  /** Alerts sorted so the highest risk is at the top of the analyst queue (business rule 7). */
  queue(): Alert[] {
    return [...this.alerts.values()].sort((a, b) => b.riskScore - a.riskScore || a.alertId.localeCompare(b.alertId));
  }

  private record(t: Transaction): void {
    for (const [index, key] of [[this.byAccount, t.accountId], [this.byCustomer, t.customerId]] as const) {
      const list = index.get(key) ?? [];
      list.push(t);
      index.set(key, list);
    }
  }

  private accountHistory(t: Transaction, hours: number): Transaction[] {
    const from = t.occurredAt.getTime() - hours * HOUR_MS;
    const to = t.occurredAt.getTime();
    return (this.byAccount.get(t.accountId) ?? [])
      .filter((x) => x.occurredAt.getTime() >= from && x.occurredAt.getTime() <= to)
      .sort((a, b) => a.occurredAt.getTime() - b.occurredAt.getTime());
  }

  threshold(t: Transaction): RuleMatch | null {
    if (!this.rules.thresholdEnabled || t.amountInr < this.rules.reportThresholdInr) return null;
    return {code: 'CTR_THRESHOLD', score: 70, explanation: 'Transaction meets or exceeds the INR reporting threshold.', evidence: [t]};
  }

  structuring(t: Transaction, history: Transaction[]): RuleMatch | null {
    if (!this.rules.structuringEnabled) return null;
    const from = t.occurredAt.getTime() - this.rules.structuringWindowHours * HOUR_MS;
    const suspicious = history.filter(
      (x) =>
        x.occurredAt.getTime() >= from &&
        x.amountInr >= this.rules.structuringMinimumInr &&
        x.amountInr < this.rules.reportThresholdInr,
    );
    if (suspicious.length < this.rules.structuringCount) return null;
    return {
      code: 'STRUCTURING',
      score: 90,
      explanation: `${suspicious.length} just-below-threshold transactions occurred within ${this.rules.structuringWindowHours} hours.`,
      evidence: suspicious,
    };
  }

  rapidMovement(t: Transaction, history: Transaction[]): RuleMatch | null {
    if (!this.rules.rapidMovementEnabled || t.type !== 'DEBIT') return null;
    const now = t.occurredAt.getTime();
    const deposits = history
      .filter((x) => x.type === 'CREDIT' && x.occurredAt.getTime() <= now && x.occurredAt.getTime() >= now - this.rules.rapidMovementHours * HOUR_MS)
      .sort((a, b) => b.occurredAt.getTime() - a.occurredAt.getTime());
    for (const deposit of deposits) {
      const outflows = history.filter(
        (x) => x.type === 'DEBIT' && x.occurredAt.getTime() >= deposit.occurredAt.getTime() && x.occurredAt.getTime() <= now,
      );
      if (sum(outflows) >= deposit.amountInr * this.rules.rapidMovementRatio) {
        return {
          code: 'RAPID_MOVEMENT',
          score: 85,
          explanation: `At least ${Math.round(this.rules.rapidMovementRatio * 100)}% of a recent deposit moved out within ${this.rules.rapidMovementHours} hours.`,
          evidence: [deposit, ...outflows],
        };
      }
    }
    return null;
  }

  highRisk(t: Transaction): RuleMatch | null {
    if (!this.rules.highRiskEnabled) return null;
    const jurisdiction = this.rules.highRiskJurisdictions.map((j) => j.toUpperCase()).includes(t.jurisdiction.toUpperCase());
    const counterparty = this.rules.highRiskCounterparties.some((c) => c.toLowerCase() === t.counterparty.toLowerCase());
    if (!jurisdiction && !counterparty) return null;
    return {
      code: 'HIGH_RISK_JURISDICTION',
      score: 95,
      explanation: 'Transaction involves a configured high-risk jurisdiction or counterparty.',
      evidence: [t],
    };
  }

  /** Customer-level: today's value or volume vs. the rolling baseline (default 3x the 90-day daily average). */
  behavioralDeviation(t: Transaction): RuleMatch | null {
    if (!this.rules.behavioralDeviationEnabled) return null;
    const dayStart = startOfUtcDay(t.occurredAt);
    const days = this.rules.behavioralBaselineDays;
    const all = this.byCustomer.get(t.customerId) ?? [];
    const baseline = all.filter((x) => x.occurredAt.getTime() >= dayStart - days * DAY_MS && x.occurredAt.getTime() < dayStart);
    if (baseline.length === 0) return null;
    const today = all.filter((x) => x.occurredAt.getTime() >= dayStart && x.occurredAt.getTime() <= t.occurredAt.getTime());

    const valueDeviation = sum(today) > (sum(baseline) / days) * this.rules.behavioralMultiplier;
    const volumeDeviation = today.length > (baseline.length / days) * this.rules.behavioralMultiplier;
    if (!valueDeviation && !volumeDeviation) return null;
    return {
      code: 'BEHAVIORAL_DEVIATION',
      score: 80,
      explanation: `Daily transaction value or volume exceeds ${this.rules.behavioralMultiplier} times the ${days}-day average.`,
      evidence: [t],
    };
  }

  roundNumber(t: Transaction, history: Transaction[]): RuleMatch | null {
    if (!this.rules.roundNumberEnabled) return null;
    const from = t.occurredAt.getTime() - 24 * HOUR_MS;
    // Compare in paise to avoid floating-point remainders.
    const unit = Math.round(this.rules.roundAmountUnitInr * 100);
    const round = history.filter((x) => x.occurredAt.getTime() >= from && Math.round(x.amountInr * 100) % unit === 0);
    if (round.length < this.rules.roundNumberCount) return null;
    return {code: 'ROUND_NUMBER', score: 45, explanation: 'Repeated round-number transactions occurred within 24 hours.', evidence: round};
  }
}

export interface DetectionRun {
  alerts: Alert[];
  transactionsEvaluated: number;
  elapsedMs: number;
}

/** Bulk run: transactions are evaluated in time order so every rule only sees earlier activity. */
export function runDetection(transactions: Transaction[], rules: RuleConfig): DetectionRun {
  const started = performance.now();
  const engine = new DetectionEngine(rules);
  const ordered = [...transactions].sort(
    (a, b) => a.occurredAt.getTime() - b.occurredAt.getTime() || a.transactionId.localeCompare(b.transactionId),
  );
  for (const t of ordered) engine.evaluate(t);
  return {alerts: engine.queue(), transactionsEvaluated: ordered.length, elapsedMs: Math.round(performance.now() - started)};
}
