import {buildAdvice} from './advice.js';
import {normalizeInput} from './guardrails.js';
import {CATEGORY_NAMES, RULES} from './rules.js';
import type {Analysis, Category, Entities, Signal, Verdict} from './types.js';
import {analyzeUrl, extractUrls} from './url.js';

const COMBO_BONUS = 10;
const MAX_LINK_WEIGHT = 50;
const SUSPICIOUS_AT = 20;
export const HIGH_RISK_AT = 45;
const SCAM_AT = 70;

function sentences(text: string): string[] {
  // Split on line breaks and sentence ends, but not on "Rs. 500" or "a.m.".
  return text.split(/\n+|(?<=[!?।])\s+|(?<=[a-z)]\.)\s+(?=[A-Z"'])/).map((s) => s.trim()).filter(Boolean);
}

function snippet(sentence: string, match: string): string {
  const start = Math.max(0, sentence.indexOf(match) - 20);
  const text = sentence.slice(start, start + 90).trim();
  return `${start > 0 ? '…' : ''}${text}${start + 90 < sentence.length ? '…' : ''}`;
}

function extractEntities(text: string): Entities {
  const unique = (m: RegExpMatchArray | null) => [...new Set(m ?? [])];
  return {
    phones: unique(text.match(/(?:\+?91[\s-]?)?\b[6-9]\d{4}[\s-]?\d{5}\b/g)),
    upiIds: unique(text.replace(/[\w.+-]+@[\w-]+(?:\.[\w-]+)+/g, ' ').match(/\b[\w.-]{2,}@[a-z]{2,}\b/gi)),
    amounts: unique(text.match(/(?:rs\.?|inr|₹)\s?\d[\d,]*(?:\.\d+)?/gi)),
  };
}

export function verdictFor(score: number): Verdict {
  if (score >= SCAM_AT) return 'Very likely a scam';
  if (score >= HIGH_RISK_AT) return 'High risk';
  if (score >= SUSPICIOUS_AT) return 'Suspicious';
  return 'Likely safe';
}

export function analyzeMessage(raw: string): Analysis {
  const input = normalizeInput(raw);
  const text = input.text;
  const signals: Signal[] = [];
  if (input.hiddenCharacters || input.directionControls) {
    signals.push({
      id: 'hidden_characters',
      category: 'obfuscation',
      weight: input.directionControls ? 40 : 25,
      label: 'Hides invisible or direction-changing characters to dodge filters',
      evidence: `${input.hiddenCharacters} invisible, ${input.directionControls} direction-control character(s)`,
    });
  }
  for (const rule of RULES) {
    for (const sentence of sentences(text)) {
      const match = sentence.match(rule.pattern);
      if (!match || rule.unless?.test(sentence)) continue;
      signals.push({id: rule.id, category: rule.category, weight: rule.weight, label: rule.label, evidence: snippet(sentence, match[0])});
      break;
    }
  }

  const urls = extractUrls(text).map(analyzeUrl);
  for (const u of urls.filter((u) => u.risk > 0 && !u.official)) {
    signals.push({
      id: 'risky_link',
      category: 'link_risk',
      weight: Math.min(u.risk, MAX_LINK_WEIGHT),
      label: `Risky link: ${u.reasons[0]}`,
      evidence: u.url,
    });
  }

  const tactics = new Set(signals.map((s) => s.category).filter((c) => c !== 'pressure'));
  let score = signals.reduce((sum, s) => sum + s.weight, 0);
  if (tactics.size >= 2 || (tactics.size === 1 && signals.some((s) => s.category === 'pressure'))) {
    score += COMBO_BONUS;
  }
  score = Math.min(100, score);

  const ranked = signals
    .filter((s) => !['pressure', 'contact_switch'].includes(s.category))
    // The scam's story (KYC, parcel, police...) describes it better than the link it uses.
    .sort((a, b) => Number(a.category === 'link_risk') - Number(b.category === 'link_risk') || b.weight - a.weight);
  const scamType = score >= SUSPICIOUS_AT && ranked[0] ? CATEGORY_NAMES[ranked[0].category] : null;
  const categories: Category[] = signals.map((s) => s.category);

  return {
    score,
    verdict: verdictFor(score),
    scamType,
    signals,
    urls,
    entities: extractEntities(text),
    advice: buildAdvice(categories, score >= SUSPICIOUS_AT),
    inputWarnings: input.warnings,
  };
}
