import type {CaseFile, Recommendation} from './investigation.js';
import {RECOMMENDATION_RANK} from './investigation.js';
import {scrubCustomerPii} from './pii.js';
import type {Customer} from './types.js';

const MAX_OUTPUT_CHARS = 6_000;
const RECOMMENDATION_LINE = /^\s*\**RECOMMENDATION:?\**\s*:?\s*(CLOSE_FALSE_POSITIVE|INVESTIGATE|ESCALATE)\b.*$/im;
// Record IDs in the sample data look like TXN_000001, ACC_000001, CUST_00001.
const RECORD_ID = /\b[A-Z]{2,6}_\d{3,}\b/g;
// The agent only drafts; filing with the FIU is a human decision.
const CLAIMS_FILING = /\b(has been|have been|was|were|is now)\s+(filed|submitted|reported to (the )?FIU)\b/i;

export interface GuardResult {
  text: string;
  recommendation: Recommendation;
  modelRecommendation: Recommendation | null;
  corrections: string[];
  rejected?: string;
}

/** Validates the model's investigation before an analyst sees it. Unsafe answers are rejected, not patched. */
export function guardInvestigation(raw: string, file: CaseFile, customers: Iterable<Customer>): GuardResult {
  const floor = file.alert.minimumRecommendation;
  const corrections: string[] = [];
  let text = raw.trim();
  const reject = (reason: string): GuardResult => ({text, recommendation: floor, modelRecommendation: null, corrections, rejected: reason});
  if (!text) return reject('the model returned an empty answer');

  const match = text.match(RECOMMENDATION_LINE);
  const modelRecommendation = (match?.[1] as Recommendation | undefined) ?? null;
  if (match) text = text.replace(match[0], '').trim();
  else corrections.push(`The model skipped the RECOMMENDATION line; the rule-based minimum (${floor}) is used.`);

  if (modelRecommendation && RECOMMENDATION_RANK[modelRecommendation] < RECOMMENDATION_RANK[floor]) {
    return reject(`the model recommended ${modelRecommendation}, below the required minimum ${floor} for this alert`);
  }
  // Seen live: a model replied only "0.25". An answer without the narrative section is not an investigation.
  if (!/draft\s+(sar|str)/i.test(text)) return reject('the answer is missing the required draft SAR/STR narrative');

  const known = new Set([
    file.alert.alertId,
    ...file.timeline.map((t) => t.transactionId),
    file.account?.accountId ?? '',
    file.customer?.customerId ?? '',
    ...(file.customer?.otherAccountIds ?? []),
  ]);
  const invented = [...new Set(text.match(RECORD_ID) ?? [])].filter((id) => !known.has(id));
  if (invented.length) return reject(`the answer cites records that are not in the case file: ${invented.join(', ')}`);

  if (CLAIMS_FILING.test(text)) return reject('the answer claims a report was filed; the agent may only draft');

  const scrubbed = scrubCustomerPii(text, customers);
  if (scrubbed !== text) corrections.push('Removed customer identifiers from the answer.');
  text = scrubbed;

  if (!/DRAFT for analyst review/i.test(text)) {
    text = `> DRAFT for analyst review. Not filed.\n\n${text}`;
    corrections.push('Added the missing DRAFT label.');
  }
  if (text.length > MAX_OUTPUT_CHARS) {
    text = `${text.slice(0, MAX_OUTPUT_CHARS)}…`;
    corrections.push('Trimmed an overly long answer.');
  }

  const recommendation = modelRecommendation ?? floor;
  return {text, recommendation, modelRecommendation, corrections};
}
