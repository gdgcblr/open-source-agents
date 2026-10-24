import {redact} from './privacy.js';
import type {Analysis, Verdict} from './types.js';

export const MAX_INPUT_CHARS = 5_000;
const MAX_OUTPUT_CHARS = 4_000;
// Zero-width space, word joiner, BOM and soft hyphen. ZWJ/ZWNJ are kept because Indic scripts need them.
const INVISIBLE = /[\u200B\u2060\uFEFF\u00AD]/g;
const BIDI_CONTROLS = /[\u202A-\u202E\u2066-\u2069]/g;
const HELPLINES = new Set(['1930', '112', '100']);

export const VERDICT_RANK: Record<Verdict, number> = {
  'Likely safe': 0,
  Suspicious: 1,
  'High risk': 2,
  'Very likely a scam': 3,
};
const VERDICT_LINE = /^\s*\**VERDICT:?\**\s*:?\s*(Likely safe|Suspicious|High risk|Very likely a scam)\b.*$/im;
const UNSAFE_ADVICE =
  /\b(it is|it's|this is|looks?) (safe|fine|ok(ay)?) to (click|open|tap|call|pay|share|install|reply)\b|\b(you can|go ahead and|feel free to) (click|open|tap|share|send|pay|install)\b|\b(share|send|tell|give)\b[^.?!]{0,20}\b(the|your) (otp|pin|cvv|password)\b/i;
const NEGATION = /\b(never|not|don't|do not|avoid|without)\b/i;

function containsUnsafeAdvice(text: string): boolean {
  return text
    .split(/\n+|(?<=[.!?।])\s+/)
    .some((sentence) => UNSAFE_ADVICE.test(sentence) && !NEGATION.test(sentence));
}

export interface NormalizedInput {
  text: string;
  hiddenCharacters: number;
  directionControls: number;
  warnings: string[];
}

/** Undoes common filter-evasion tricks before any rule or model sees the text. */
export function normalizeInput(raw: string): NormalizedInput {
  const hiddenCharacters = raw.match(INVISIBLE)?.length ?? 0;
  const directionControls = raw.match(BIDI_CONTROLS)?.length ?? 0;
  // NFKC folds look-alike forms such as full-width "ＯＴＰ" into plain "OTP".
  let text = raw.replace(INVISIBLE, '').replace(BIDI_CONTROLS, '').normalize('NFKC').replace(/\r\n?/g, '\n').trim();

  const warnings: string[] = [];
  if (text.length > MAX_INPUT_CHARS) {
    text = text.slice(0, MAX_INPUT_CHARS);
    warnings.push(`Message was longer than ${MAX_INPUT_CHARS} characters; only the first ${MAX_INPUT_CHARS} were analysed.`);
  }
  if (hiddenCharacters) warnings.push(`Removed ${hiddenCharacters} invisible character(s) used to slip words past filters.`);
  if (directionControls) warnings.push(`Removed ${directionControls} text-direction control character(s) used to disguise links.`);
  return {text, hiddenCharacters, directionControls, warnings};
}

export function defang(url: string): string {
  return url.replace(/^http/i, 'hxxp').replace(/\./g, '[.]');
}

/** Replaces every risky link in `text` with its non-clickable form. */
export function defangLinks(text: string, analysis: Analysis): string {
  let out = text;
  for (const u of analysis.urls.filter((u) => !u.official)) {
    out = out.split(u.url).join(u.defanged);
    if (u.host) out = out.split(u.host).join(defang(u.host));
  }
  return out;
}

export interface GuardResult {
  text: string;
  modelVerdict: Verdict | null;
  corrections: string[];
  /** Set when the answer must not be shown at all; the caller falls back. */
  rejected?: string;
}

/** Checks the model's answer before a user sees it. Fails closed: anything unsafe is rejected, not patched. */
export function guardExplanation(raw: string, analysis: Analysis, originalMessage: string): GuardResult {
  const corrections: string[] = [];
  let text = raw.trim();
  if (!text) return {text, modelVerdict: null, corrections, rejected: 'the model returned an empty answer'};

  const match = text.match(VERDICT_LINE);
  const modelVerdict = (match?.[1] as Verdict | undefined) ?? null;
  if (match) text = text.replace(match[0], '').trim();
  else corrections.push('The model skipped the required VERDICT line; the rule verdict is used.');

  if (modelVerdict && VERDICT_RANK[modelVerdict] < VERDICT_RANK[analysis.verdict]) {
    return {
      text,
      modelVerdict,
      corrections,
      rejected: `the model rated it "${modelVerdict}", safer than the rule verdict "${analysis.verdict}"`,
    };
  }
  if (VERDICT_RANK[analysis.verdict] >= VERDICT_RANK.Suspicious && containsUnsafeAdvice(text)) {
    return {text, modelVerdict, corrections, rejected: 'the answer contained unsafe advice for a risky message'};
  }

  const masked = maskEchoedSecrets(text, originalMessage);
  if (masked !== text) corrections.push('Masked codes or numbers that the model copied from the message.');
  const defanged = defangLinks(masked, analysis);
  if (defanged !== masked) corrections.push('Made risky links non-clickable.');
  text = defanged;

  if (text.length > MAX_OUTPUT_CHARS) {
    text = `${text.slice(0, MAX_OUTPUT_CHARS)}…`;
    corrections.push('Trimmed an overly long answer.');
  }
  return {text, modelVerdict, corrections};
}

function maskEchoedSecrets(text: string, originalMessage: string): string {
  const codes = (originalMessage.match(/\b\d{4,8}\b/g) ?? []).filter((c) => !HELPLINES.has(c));
  let out = redact(text);
  for (const code of new Set(codes)) out = out.replace(new RegExp(`\\b${code}\\b`, 'g'), '[CODE]');
  return out;
}
