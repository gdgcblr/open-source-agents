import {defang} from './guardrails.js';
import type {UrlReport} from './types.js';

// Official domains for brands that scammers commonly impersonate in India. Extend as needed.
export const OFFICIAL_DOMAINS: Record<string, string[]> = {
  sbi: ['sbi.co.in', 'onlinesbi.sbi', 'sbicard.com'],
  hdfc: ['hdfcbank.com'],
  icici: ['icicibank.com'],
  axis: ['axisbank.com'],
  kotak: ['kotak.com'],
  paytm: ['paytm.com'],
  phonepe: ['phonepe.com'],
  amazon: ['amazon.in', 'amazon.com'],
  flipkart: ['flipkart.com'],
  indiapost: ['indiapost.gov.in'],
  incometax: ['incometax.gov.in'],
  uidai: ['uidai.gov.in'],
  aadhaar: ['uidai.gov.in'],
  irctc: ['irctc.co.in'],
  npci: ['npci.org.in'],
  epfo: ['epfindia.gov.in'],
  whatsapp: ['whatsapp.com'],
  netflix: ['netflix.com'],
};

const SHORTENERS = new Set([
  'bit.ly', 'tinyurl.com', 't.co', 'goo.gl', 'is.gd', 'cutt.ly', 'rb.gy', 'shorturl.at',
  't.ly', 'tiny.cc', 'ow.ly', 'rebrand.ly', 'shorte.st', 'v.gd', 'bitly.com',
]);
const PRIVATE_CHAT_HOSTS = new Set(['wa.me', 't.me', 'telegram.me', 'chat.whatsapp.com']);
const RISKY_TLDS = new Set([
  'xyz', 'top', 'click', 'link', 'site', 'online', 'live', 'shop', 'icu', 'buzz', 'loan',
  'win', 'vip', 'cc', 'tk', 'ml', 'ga', 'cf', 'gq', 'rest', 'cyou', 'sbs', 'cfd', 'monster',
]);
const SECOND_LEVEL_SUFFIXES = new Set(['co', 'gov', 'org', 'net', 'ac', 'nic', 'res', 'edu', 'com']);
const BARE_TLDS = 'com|in|net|org|co|info|io|me|app|xyz|top|click|link|site|online|live|shop|icu|buzz|loan|win|vip|cc|tk|ml|ga|cf|gq|rest|cyou|sbs|cfd|sbi';

const SCHEME_URL = /\bhttps?:\/\/[^\s<>"'\]]+/gi;
const EMAIL = /[\w.+-]+@[\w-]+(?:\.[\w-]+)+/g;
const BARE_URL = new RegExp(
  String.raw`\bwww\.[^\s<>"'\]]+|\b[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.(?:${BARE_TLDS})\b(?:\/[^\s<>"'\]]*)?`,
  'gi',
);

export function extractUrls(text: string): string[] {
  const withScheme = text.match(SCHEME_URL) ?? [];
  const rest = text.replace(SCHEME_URL, ' ').replace(EMAIL, ' ');
  const found = [...withScheme, ...(rest.match(BARE_URL) ?? [])].map((u) => u.replace(/[.,;:!?)'"]+$/, ''));
  return [...new Set(found)];
}

/** Naive registrable domain: handles two-level suffixes such as .co.in and .gov.in. */
export function registrableDomain(host: string): string {
  const labels = host.split('.');
  if (labels.length >= 3 && SECOND_LEVEL_SUFFIXES.has(labels[labels.length - 2]) && labels[labels.length - 1].length === 2) {
    return labels.slice(-3).join('.');
  }
  return labels.slice(-2).join('.');
}

function levenshtein(a: string, b: string): number {
  const row = Array.from({length: b.length + 1}, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    let prev = row[0];
    row[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const temp = row[j];
      row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1));
      prev = temp;
    }
  }
  return row[b.length];
}

function officialBrandFor(host: string): string | null {
  for (const [brand, domains] of Object.entries(OFFICIAL_DOMAINS)) {
    if (domains.some((d) => host === d || host.endsWith(`.${d}`))) return brand;
  }
  return null;
}

export function analyzeUrl(raw: string): UrlReport {
  const withScheme = /^https?:\/\//i.test(raw) ? raw : `http://${raw}`;
  let parsed: URL;
  try {
    parsed = new URL(withScheme);
  } catch {
    return {url: raw, defanged: defang(raw), host: '', risk: 30, official: false, reasons: ['Malformed link']};
  }
  const host = parsed.hostname.toLowerCase().replace(/^www\./, '');
  const found: {points: number; reason: string}[] = [];
  const add = (points: number, reason: string) => found.push({points, reason});

  const official = officialBrandFor(host);
  if (official) {
    const risk = /^http:\/\//i.test(raw) ? 10 : 0;
    const reasons = [`Official ${official.toUpperCase()} domain`, ...(risk ? ['Uses plain http instead of https'] : [])];
    return {url: raw, defanged: raw, host, risk, official: true, reasons};
  }

  if (SHORTENERS.has(host)) add(30, 'Link shortener hides the real destination');
  if (PRIVATE_CHAT_HOSTS.has(host)) add(20, 'Moves you to a private WhatsApp/Telegram chat with an unknown person');
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(host)) add(40, 'Uses a raw IP address instead of a domain name');
  if (host.split('.').some((l) => l.startsWith('xn--'))) add(40, 'Uses look-alike international characters (punycode)');
  if (RISKY_TLDS.has(host.split('.').pop() ?? '')) add(25, `Uses a cheap domain ending often used in scams (.${host.split('.').pop()})`);
  if (parsed.username || raw.includes('@')) add(30, 'Contains "@", which can disguise the real destination');
  if (host.split('.').length > 4) add(10, 'Has an unusually deep chain of sub-domains');
  if (/\.apk(?:$|[?#])/i.test(parsed.pathname + parsed.search)) add(40, 'Downloads an Android app (APK) directly');

  const tokens = host.split(/[.-]/);
  const mainLabel = registrableDomain(host).split('.')[0];
  for (const [brand, domains] of Object.entries(OFFICIAL_DOMAINS)) {
    const mentions = tokens.some((t) => (brand.length >= 4 ? t.includes(brand) : t === brand || t.startsWith(brand) || t.endsWith(brand)));
    if (mentions) {
      add(45, `Mentions "${brand}" but is not an official ${brand.toUpperCase()} domain (${domains[0]})`);
      break;
    }
    const officialLabels = domains.map((d) => d.split('.')[0]);
    if (mainLabel.length >= 4 && officialLabels.some((l) => l !== mainLabel && levenshtein(l, mainLabel) === 1)) {
      add(45, `Looks like a misspelling of ${domains[0]}`);
      break;
    }
  }
  found.sort((a, b) => b.points - a.points);
  const risk = Math.min(100, found.reduce((sum, f) => sum + f.points, 0));
  return {url: raw, defanged: defang(raw), host, risk, official: false, reasons: found.map((f) => f.reason)};
}
