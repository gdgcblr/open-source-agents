import type {Category} from './types.js';

export interface Rule {
  id: string;
  category: Category;
  weight: number;
  label: string;
  pattern: RegExp;
  /** If this also matches the same sentence, the rule is ignored (e.g. "never share your OTP"). */
  unless?: RegExp;
}

// Devanagari alternatives sit outside \b groups because \b only understands ASCII word characters.
export const RULES: Rule[] = [
  {
    id: 'urgency',
    category: 'pressure',
    weight: 15,
    label: 'Creates urgency so you act before thinking',
    pattern: /\b(immediately|urgent(ly)?|within \d+ ?(hours?|hrs?|minutes?|mins?)|today itself|last (chance|warning|reminder|date today)|act now|tonight|right now|jaldi|turant|limited (time|period|offer)|only for (the )?first \d+)\b|तुरंत|जल्दी/i,
  },
  {
    id: 'secrecy',
    category: 'pressure',
    weight: 20,
    label: 'Tells you to keep it secret from family or your bank',
    pattern: /\b(do not|don't|dont)\b[^.?!]{0,15}\b(tell|inform|share (this|it) with)\b[^.?!]{0,20}\b(anyone|anybody|family|bank|police)\b|\bkeep (this|it) (confidential|secret)\b|किसी को (मत|न) बताएं/i,
  },
  {
    id: 'impersonation',
    category: 'impersonation',
    weight: 20,
    label: 'Claims to be an army officer or official to win your trust',
    pattern: /\b(i am|i'm|this is)\b[^.?!]{0,20}\b(army|crpf|bsf|cisf|air force|navy|military|bank manager|rbi officer|government officer)\b/i,
  },
  {
    id: 'otp_request',
    category: 'otp_or_pin',
    weight: 35,
    label: 'Asks you to share an OTP, PIN, CVV or password',
    pattern: /\b(share|send|tell|provide|forward|give|reply with|confirm)\b[^.?!]{0,40}\b(otp|upi pin|atm pin|pin|cvv|password|one[- ]time password)\b|\botp\b[^.?!]{0,20}\b(batao|bhejo|batayein|share karein)\b|ओटीपी[^.?!]{0,20}(बताएं|भेजें)/i,
    unless: /\b(never|do not|don't|dont|not to|no one|nobody|kabhi|delivery (partner|agent|executive)|at the time of delivery)\b|कभी/i,
  },
  {
    id: 'kyc_block',
    category: 'kyc_or_account_block',
    weight: 25,
    label: 'Threatens to block your account or demands a KYC/PAN/Aadhaar update',
    pattern: /\b(kyc|pan( card)?|aadhaar)\b[^.?!]{0,40}\b(update|expired?|pending|verify|verification|link(ed)?|suspend(ed)?)\b|\b(account|card|wallet|sim)\b[^.?!]{0,30}\b(block(ed)?|suspend(ed)?|freez(e|ed)|frozen|deactivat\w*|clos(e|ed)|band)\b|खाता[^.?!]{0,20}बंद/i,
  },
  {
    id: 'digital_arrest',
    category: 'digital_arrest',
    weight: 40,
    label: 'Claims police, CBI, customs or a court case against you ("digital arrest")',
    pattern: /\b(digital arrest|arrest warrant|cbi|narcotics|ncb|enforcement directorate|money laundering|customs (officer|department)|cyber ?cell|crime branch|trai|fir (has been|is|was) (registered|filed|lodged)|illegal (items|drugs|passports?))\b|गिरफ्तार/i,
  },
  {
    id: 'utility_disconnection',
    category: 'utility_disconnection',
    weight: 35,
    label: 'Threatens to cut your electricity, gas or connection',
    pattern: /\b(electricity|power|bijli|light|gas|connection)\b[^.?!]{0,60}\b(disconnect\w*|cut|discontinu\w*|will be (stopped|cut|disconnected))\b|बिजली[^.?!]{0,40}(कट|काट)/i,
  },
  {
    id: 'prize',
    category: 'prize_or_lottery',
    weight: 30,
    label: 'Says you won a prize, lottery or reward you never entered',
    pattern: /\b(you (have )?won|winner|lottery|lucky draw|jackpot|kbc|kaun banega|prize money|cash prize|reward of|cashback of)\b|इनाम|लॉटरी/i,
  },
  {
    id: 'task_job',
    category: 'job_or_task',
    weight: 30,
    label: 'Offers easy money for simple online tasks or part-time work',
    pattern: /\b(work from home|part[- ]time (job|work)|earn (rs\.?|₹|inr)? ?\d[\d,]*|daily (income|earning|payout)|lik(e|ing) (youtube )?videos|rat(e|ing) (hotels|products|movies)|telegram task|prepaid task|per task)\b/i,
  },
  {
    id: 'investment',
    category: 'investment',
    weight: 30,
    label: 'Promises guaranteed or very high investment returns',
    pattern: /\b(guaranteed (returns?|profits?|income)|double your money|\d+ ?% (daily|weekly|monthly|per day|per week) (returns?|profits?)|crypto (trading|investment)|stock tips|vip (trading|stock) group|ipo allotment)\b/i,
  },
  {
    id: 'parcel',
    category: 'parcel_or_customs',
    weight: 25,
    label: 'Says a parcel is held, seized or cannot be delivered',
    pattern: /\b(parcel|courier|shipment|package)\b[^.?!]{0,90}\b(held|seized|on hold|customs|undeliver\w*|incomplete address|address (is )?incomplete|redeliver\w*|failed|returned)\b/i,
  },
  {
    id: 'pin_to_receive',
    category: 'payment_trick',
    weight: 40,
    label: 'Asks for your UPI PIN or a QR scan to "receive" money (PINs are only for paying)',
    pattern: /\b(enter|use)\b[^.?!]{0,20}\b(upi )?pin\b[^.?!]{0,30}\b(receive|get|credit|claim)\b|\bscan\b[^.?!]{0,30}\bqr\b[^.?!]{0,30}\b(receive|get|credit|claim)\b|\b(accept|approve)\b[^.?!]{0,20}\bcollect request\b/i,
  },
  {
    id: 'refund_bait',
    category: 'payment_trick',
    weight: 20,
    label: 'Dangles a refund or payment that you must "claim" through a link or call',
    pattern: /\b(claim|process|get|receive)\b[^.?!]{0,15}\brefund\b|\brefund\b[^.?!]{0,30}\b(click|link|call|contact)\b/i,
  },
  {
    id: 'unusual_payment',
    category: 'payment_trick',
    weight: 20,
    label: 'Asks for payment by gift card, crypto or a "processing fee"',
    pattern: /\b(gift ?cards?|google play (card|recharge|code)|usdt|bitcoin|crypto wallet|processing fee|registration fee|release fee|clearance fee)\b/i,
  },
  {
    id: 'remote_access',
    category: 'remote_access',
    weight: 40,
    label: 'Asks you to install an app or APK that can control your phone',
    pattern: /\b(anydesk|teamviewer|quick ?support|rustdesk|airdroid|screen ?shar\w*)\b|\.apk\b|\b(download|install)\b[^.?!]{0,20}\b(this|the|our|below)\b[^.?!]{0,10}\bapp\b/i,
  },
  {
    id: 'personal_number',
    category: 'contact_switch',
    weight: 15,
    label: 'Asks you to call or WhatsApp a personal mobile number',
    pattern: /\b(call|contact|whatsapp|message|sms|reach)\b[^.?!]{0,40}(\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}\b/i,
  },
  {
    id: 'ai_manipulation',
    category: 'manipulation',
    weight: 35,
    label: 'Contains hidden instructions aimed at AI scam checkers',
    pattern: /\b(ignore|disregard|forget|override)\b[^.?!]{0,30}\b(previous|above|prior|all|earlier|your)\b[^.?!]{0,20}\b(instructions?|rules?|prompts?|guidelines)\b|\b(system prompt|note to (the )?(ai|assistant|model)|as an ai)\b|\b(classify|mark|rate|label|treat|report)\b[^.?!]{0,30}\b(this|message|it)\b[^.?!]{0,20}\b(as )?(safe|legit(imate)?|genuine|not (a )?scam)\b/i,
  },
];

export const CATEGORY_NAMES: Record<string, string> = {
  manipulation: 'Attempt to fool AI checkers',
  obfuscation: 'Hidden-character obfuscation',
  pressure: 'Pressure tactics',
  otp_or_pin: 'OTP / PIN theft',
  kyc_or_account_block: 'Fake KYC / account block',
  digital_arrest: '"Digital arrest" / fake police',
  utility_disconnection: 'Fake electricity disconnection',
  prize_or_lottery: 'Fake prize / lottery',
  job_or_task: 'Task / part-time job scam',
  investment: 'Investment scam',
  parcel_or_customs: 'Fake parcel / customs',
  payment_trick: 'UPI / payment trick',
  remote_access: 'Remote-access app scam',
  contact_switch: 'Move to personal number',
  impersonation: 'Impersonation',
  link_risk: 'Phishing link',
};
