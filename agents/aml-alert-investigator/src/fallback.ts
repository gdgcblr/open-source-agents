import type {CaseFile} from './investigation.js';

const RULE_TEXT: Record<string, string> = {
  CTR_THRESHOLD: 'a single transaction at or above the INR reporting threshold',
  STRUCTURING: 'several transactions just below the reporting threshold in a short window, consistent with structuring',
  RAPID_MOVEMENT: 'most of a recent deposit moved out shortly after it arrived, consistent with layering',
  HIGH_RISK_JURISDICTION: 'a transaction involving a configured high-risk jurisdiction or counterparty',
  BEHAVIORAL_DEVIATION: "activity far above the customer's own recent baseline",
  ROUND_NUMBER: 'repeated round-number amounts',
};

const formatInr = (n: number | null | undefined) =>
  n === null || n === undefined ? 'not provided' : `INR ${n.toLocaleString('en-IN', {maximumFractionDigits: 2})}`;

/**
 * Deterministic investigation note used when Gemini is unavailable or its answer is rejected.
 * It only restates facts from the case file, so it cannot invent evidence.
 */
export function fallbackInvestigation(file: CaseFile, reason: string): string {
  const {alert, customer, account, evidence, totals} = file;
  const first = evidence[0]?.occurredAt.slice(0, 10);
  const last = evidence.at(-1)?.occurredAt.slice(0, 10);
  const period = first === last ? `on ${first}` : `between ${first} and ${last}`;
  const lines = [
    `**Recommendation:** ${alert.minimumRecommendation} (rule-based minimum for risk ${alert.riskScore}/100)`,
    '',
    '**Red flags**',
    ...alert.ruleCodes.map((code) => `- ${code}: ${RULE_TEXT[code] ?? code}.`),
    '',
    '**Evidence**',
    ...evidence.map(
      (t) => `- ${t.transactionId} · ${t.occurredAt.slice(0, 16).replace('T', ' ')} UTC · ${t.type} · ${formatInr(t.amountInr)} · ${t.counterparty || 'unknown counterparty'} · ${t.channel} · ${t.jurisdiction}`,
    ),
    '',
    '**Draft SAR narrative** (DRAFT for analyst review. Not filed.)',
    '',
    `Account ${account?.accountId ?? alert.alertId} (${account?.accountType ?? 'unknown type'}), held by customer ${customer?.customerId ?? 'unknown'} ` +
      `(${customer?.maskedName ?? 'name withheld'}; KYC ${customer?.kycStatus || 'unknown'}, risk rating ${customer?.riskRating ?? 'unknown'}, ` +
      `declared annual income ${formatInr(customer?.declaredAnnualIncomeInr)}), recorded ${evidence.length} flagged transaction(s) totalling ` +
      `${formatInr(totals.evidenceInr)} ${period}. The monitoring system flagged ${alert.ruleCodes.map((c) => RULE_TEXT[c] ?? c).join('; ')}. ` +
      `For comparison, the account's six-month average monthly balance is ${formatInr(account?.avgMonthlyBalance6mInr)}. ` +
      `Jurisdictions involved: ${totals.jurisdictions.join(', ')}.`,
    '',
    '**Questions for the analyst**',
    '- What is the documented source of funds for the flagged credits?',
    '- Is there a business relationship with the listed counterparties?',
    ...(customer?.otherAccountIds.length ? [`- Review linked account(s) ${customer.otherAccountIds.join(', ')} for related activity.`] : []),
    '',
    `_(Gemini investigation unavailable: ${reason}. This note was generated from the case file only.)_`,
  ];
  return lines.join('\n');
}
