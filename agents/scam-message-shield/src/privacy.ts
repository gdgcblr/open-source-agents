const URL_LIKE = /\bhttps?:\/\/[^\s]+|\bwww\.[^\s]+/gi;
const REDACTIONS: [RegExp, string][] = [
  [/[\w.+-]+@[\w-]+(?:\.[\w-]+)+/g, '[EMAIL]'],
  [/\b[\w.-]{2,}@[a-z]{2,}\b/gi, '[UPI_ID]'],
  [/(?:\+?91[\s-]?)?\b[6-9]\d{4}[\s-]?\d{5}\b/g, '[PHONE]'],
  [/\b\d(?:[\s-]?\d){8,17}\b/g, '[NUMBER]'],
];

/**
 * Masks phone numbers, emails, UPI IDs and long account/card numbers before text leaves the machine.
 * Links are kept because they are needed for the analysis.
 */
export function redact(text: string): string {
  const urls: string[] = [];
  let masked = text.replace(URL_LIKE, (u) => `\u0000${urls.push(u) - 1}\u0000`);
  for (const [pattern, label] of REDACTIONS) masked = masked.replace(pattern, label);
  return masked.replace(/\u0000(\d+)\u0000/g, (_, i: string) => urls[Number(i)]);
}
