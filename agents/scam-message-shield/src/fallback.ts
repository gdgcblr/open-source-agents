import type {Analysis, Verdict} from './types.js';

const DEVANAGARI = /[\u0900-\u097F]/g;
const LATIN = /[A-Za-z]/g;

const HINDI_VERDICT: Record<Verdict, string> = {
  'Likely safe': 'शायद सुरक्षित',
  Suspicious: 'संदिग्ध',
  'High risk': 'उच्च जोखिम',
  'Very likely a scam': 'लगभग निश्चित रूप से धोखाधड़ी',
};

export function isMostlyHindi(text: string): boolean {
  const words = text.replace(/\b(?:https?:\/\/|www\.)\S+/gi, ' ');
  const hindi = words.match(DEVANAGARI)?.length ?? 0;
  const latin = words.match(LATIN)?.length ?? 0;
  return hindi > latin;
}

/**
 * Deterministic explanation used whenever Gemini is unavailable or its answer is rejected.
 * English users already get the full rule report, so only non-English messages need a translated summary.
 */
export function fallbackExplanation(analysis: Analysis, message: string, reason: string): string {
  const note = `Gemini explanation unavailable (${reason}). The rule-based result above was produced offline and is complete.`;
  if (!isMostlyHindi(message)) return note;

  const risky = analysis.score >= 20;
  const lines = [
    `**निर्णय:** ${HINDI_VERDICT[analysis.verdict]} (${analysis.score}/100)`,
    ...(analysis.scamType ? [`**प्रकार:** ${analysis.scamType}`] : []),
    '',
    ...(risky
      ? [
          '- इस संदेश के किसी भी लिंक पर क्लिक न करें, दिए गए नंबर पर कॉल न करें, और कोई OTP, PIN या पासवर्ड साझा न करें।',
          '- कोई भी बैंक या सरकारी विभाग कभी आपका OTP, PIN या CVV नहीं मांगता।',
          '- KYC या खाते से जुड़ा काम सिर्फ बैंक के आधिकारिक ऐप या शाखा में करें।',
          '- शिकायत के लिए 1930 पर कॉल करें या cybercrime.gov.in पर जाएं। अगर पैसे कट गए हैं तो तुरंत 1930 और अपने बैंक को कॉल करें।',
        ]
      : ['- कोई बड़ा खतरे का संकेत नहीं मिला। संदेह हो तो आधिकारिक ऐप या वेबसाइट से संपर्क करें।']),
    '',
    `_(${note})_`,
  ];
  return lines.join('\n');
}

export function failSafeMessage(): string {
  return [
    'Verdict: COULD NOT ANALYSE. Treat this message as suspicious.',
    '  - Do not click links, call numbers, or share any OTP, PIN or password from it.',
    '  - Contact the organisation only through its official app or website.',
    '  - Report suspected fraud: call 1930 or visit cybercrime.gov.in.',
  ].join('\n');
}
