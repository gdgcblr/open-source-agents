export type TransactionType = 'CREDIT' | 'DEBIT';

export type RuleCode =
  | 'CTR_THRESHOLD'
  | 'STRUCTURING'
  | 'RAPID_MOVEMENT'
  | 'HIGH_RISK_JURISDICTION'
  | 'BEHAVIORAL_DEVIATION'
  | 'ROUND_NUMBER';

export interface Customer {
  customerId: string;
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
  dateOfBirth: string;
  country: string;
  occupation: string;
  annualIncome: number | null;
  segment: string;
  kycStatus: string;
  riskRating: string;
  politicallyExposed: boolean;
  customerSince: string;
}

export interface Account {
  accountId: string;
  customerId: string;
  accountType: string;
  status: string;
  currency: string;
  openDate: string;
  branchCity: string;
  avgMonthlyBalance6m: number | null;
  avgMonthlyTxnCount: number | null;
}

export interface Transaction {
  transactionId: string;
  accountId: string;
  customerId: string;
  type: TransactionType;
  amount: number;
  currency: string;
  /** Amount normalised to INR with the configured exchange-rate table (business rule 9). */
  amountInr: number;
  counterparty: string;
  channel: string;
  jurisdiction: string;
  occurredAt: Date;
}

export interface RuleMatch {
  code: RuleCode;
  score: number;
  explanation: string;
  evidence: Transaction[];
}

export interface Alert {
  alertId: string;
  /** account:rules:UTC-day, so one pattern on one day yields one alert (aggregation). */
  dedupeKey: string;
  customerId: string;
  accountId: string;
  ruleCodes: RuleCode[];
  riskScore: number;
  explanation: string;
  evidenceIds: string[];
  status: 'OPEN';
}

export interface Dataset {
  customers: Map<string, Customer>;
  accounts: Map<string, Account>;
  transactions: Transaction[];
  errors: string[];
  duplicatesSkipped: number;
}
