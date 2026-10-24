import type {Category} from './types.js';

const CATEGORY_ADVICE: Partial<Record<Category, string>> = {
  otp_or_pin: 'No bank, wallet, or government office will ever ask for your OTP, PIN, CVV or password.',
  kyc_or_account_block: 'Update KYC only in your bank\'s official app or at a branch, never through a link or a phone call.',
  digital_arrest: 'Police, CBI, ED and customs never "arrest" people on a video call or ask for money to close a case. Hang up and report it.',
  utility_disconnection: 'Check your bill only in your electricity board\'s official app or website. Real boards don\'t send notices from personal mobile numbers.',
  prize_or_lottery: 'You cannot win a lottery you never entered. Never pay a "processing fee" to claim a prize.',
  job_or_task: 'Real jobs don\'t pay you to like videos or rate hotels, and never ask you to deposit money to unlock your earnings.',
  investment: 'Guaranteed high returns are a classic warning sign. Check that the advisor is registered on the SEBI website.',
  parcel_or_customs: 'Track parcels only on the courier\'s official website. Type the address yourself instead of using a link.',
  payment_trick: 'You never need your UPI PIN or a QR scan to RECEIVE money. A PIN is only for paying.',
  remote_access: 'Never install AnyDesk, TeamViewer or an APK because a stranger asked. These apps can take full control of your phone.',
  contact_switch: 'Contact your bank or service provider only through the number on its official website or the back of your card.',
  impersonation: 'Scammers often pose as army officers, bank managers or officials. Verify identity through official channels before acting.',
  manipulation: 'This message contains text written to trick AI tools into calling it safe. Genuine messages never do this.',
  obfuscation: 'This message hides invisible or direction-changing characters, a trick used to slip past spam filters or disguise links.',
  link_risk: 'Don\'t tap the link. Open the official website by typing its address yourself.',
};

export const REPORTING_ADVICE =
  'In India, report it on the National Cyber Crime Helpline 1930 or at cybercrime.gov.in, and report the sender through Chakshu on sancharsaathi.gov.in. If you already shared details or paid, call 1930 and your bank immediately.';

export function buildAdvice(categories: Category[], isRisky: boolean): string[] {
  if (!isRisky) {
    return ['No strong scam signs found. If you\'re still unsure, contact the sender through their official app or website, not through this message.'];
  }
  const specific = [...new Set(categories)].map((c) => CATEGORY_ADVICE[c]).filter((a): a is string => Boolean(a));
  return ['Don\'t click links, call numbers, or share any codes from this message.', ...specific, REPORTING_ADVICE];
}
