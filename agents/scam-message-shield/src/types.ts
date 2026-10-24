export type Category =
  | 'pressure'
  | 'otp_or_pin'
  | 'kyc_or_account_block'
  | 'digital_arrest'
  | 'utility_disconnection'
  | 'prize_or_lottery'
  | 'job_or_task'
  | 'investment'
  | 'parcel_or_customs'
  | 'payment_trick'
  | 'remote_access'
  | 'contact_switch'
  | 'impersonation'
  | 'obfuscation'
  | 'manipulation'
  | 'link_risk';

export type Verdict = 'Likely safe' | 'Suspicious' | 'High risk' | 'Very likely a scam';

export interface Signal {
  id: string;
  category: Category;
  weight: number;
  label: string;
  evidence: string;
}

export interface UrlReport {
  url: string;
  /** Non-clickable form, e.g. hxxp://sbi-kyc[.]top, safe to show to users. */
  defanged: string;
  host: string;
  risk: number;
  official: boolean;
  reasons: string[];
}

export interface Entities {
  phones: string[];
  upiIds: string[];
  amounts: string[];
}

export interface Analysis {
  score: number;
  verdict: Verdict;
  scamType: string | null;
  signals: Signal[];
  urls: UrlReport[];
  entities: Entities;
  advice: string[];
  inputWarnings: string[];
}
