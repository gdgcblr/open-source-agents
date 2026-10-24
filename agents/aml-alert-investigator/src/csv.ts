import {readFileSync} from 'node:fs';
import {join} from 'node:path';
import type {RuleConfig} from './config.js';
import type {Account, Customer, Dataset, Transaction} from './types.js';

type Row = Record<string, string>;

/** Minimal RFC 4180 parser: quoted fields, escaped quotes, commas and newlines inside quotes. */
export function parseCsv(text: string): Row[] {
  const records: string[][] = [];
  let field = '';
  let record: string[] = [];
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') {
        field += '"';
        i++;
      } else if (c === '"') {
        quoted = false;
      } else {
        field += c;
      }
    } else if (c === '"') {
      quoted = true;
    } else if (c === ',') {
      record.push(field);
      field = '';
    } else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++;
      record.push(field);
      records.push(record);
      record = [];
      field = '';
    } else {
      field += c;
    }
  }
  if (field || record.length) {
    record.push(field);
    records.push(record);
  }
  const [header, ...rows] = records.filter((r) => r.some((v) => v.trim() !== ''));
  if (!header) return [];
  return rows.map((r) => Object.fromEntries(header.map((h, i) => [h.trim(), (r[i] ?? '').trim()])));
}

function required(row: Row, key: string): string {
  const value = row[key];
  if (!value) throw new Error(`missing required field ${key}`);
  return value;
}

function optionalNumber(row: Row, key: string): number | null {
  if (!row[key]) return null;
  const n = Number(row[key]);
  if (!Number.isFinite(n)) throw new Error(`invalid number in ${key}`);
  return n;
}

function isoDate(row: Row, key: string, isRequired: boolean): string {
  const value = isRequired ? required(row, key) : row[key] ?? '';
  if (value && !/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error(`invalid date in ${key}`);
  return value;
}

export function toCustomer(row: Row): Customer {
  return {
    customerId: required(row, 'customer_id'),
    firstName: required(row, 'first_name'),
    lastName: required(row, 'last_name'),
    email: row.email ?? '',
    phone: row.phone_number ?? '',
    dateOfBirth: isoDate(row, 'date_of_birth', true),
    country: required(row, 'country'),
    occupation: row.occupation ?? '',
    annualIncome: optionalNumber(row, 'annual_income'),
    segment: row.customer_segment ?? '',
    kycStatus: row.kyc_status ?? '',
    riskRating: required(row, 'risk_rating'),
    politicallyExposed: row.is_politically_exposed === '1',
    customerSince: isoDate(row, 'customer_since', false),
  };
}

export function toAccount(row: Row, customers: Map<string, Customer>): Account {
  const customerId = required(row, 'customer_id');
  if (!customers.has(customerId)) throw new Error(`unknown customer_id ${customerId}`);
  return {
    accountId: required(row, 'account_id'),
    customerId,
    accountType: required(row, 'account_type'),
    status: required(row, 'account_status'),
    currency: required(row, 'currency').toUpperCase(),
    openDate: isoDate(row, 'open_date', true),
    branchCity: row.branch_city ?? '',
    avgMonthlyBalance6m: optionalNumber(row, 'avg_monthly_balance_6m'),
    avgMonthlyTxnCount: optionalNumber(row, 'avg_monthly_txn_count'),
  };
}

export function toTransaction(row: Row, accounts: Map<string, Account>, rules: RuleConfig): Transaction {
  const accountId = required(row, 'account_id');
  const account = accounts.get(accountId);
  if (!account) throw new Error(`unknown account_id ${accountId}`);

  const type = required(row, 'transaction_type').toUpperCase();
  if (type !== 'CREDIT' && type !== 'DEBIT') throw new Error('transaction_type must be CREDIT or DEBIT');

  const amount = Number(required(row, 'amount'));
  if (!Number.isFinite(amount) || amount <= 0) throw new Error('amount must be a positive number');

  const currency = required(row, 'currency').toUpperCase();
  const rate = rules.exchangeRatesToInr[currency];
  if (rate === undefined) throw new Error(`no INR exchange rate configured for ${currency}`);

  const timestamp = required(row, 'timestamp');
  const occurredAt = new Date(timestamp);
  if (!/^\d{4}-\d{2}-\d{2}T/.test(timestamp) || Number.isNaN(occurredAt.getTime())) {
    throw new Error('timestamp must be ISO-8601, e.g. 2026-09-18T09:00:00Z');
  }

  return {
    transactionId: required(row, 'transaction_id'),
    accountId,
    customerId: account.customerId,
    type,
    amount,
    currency,
    // Same rounding as the original: setScale(4, HALF_UP).
    amountInr: Math.round(amount * rate * 10_000) / 10_000,
    counterparty: row.counterparty ?? '',
    channel: (row.channel ?? '').toUpperCase(),
    jurisdiction: required(row, 'jurisdiction').toUpperCase(),
    occurredAt,
  };
}

/**
 * Loads customers, then accounts, then transactions (the order matters for referential integrity).
 * Malformed rows are rejected with a row-numbered error instead of failing the whole import.
 */
export function loadDataset(dir: string, rules: RuleConfig): Dataset {
  const errors: string[] = [];
  const read = (file: string) => parseCsv(readFileSync(join(dir, file), 'utf8'));
  const each = <T>(file: string, rows: Row[], convert: (row: Row) => T, add: (item: T) => void) =>
    rows.forEach((row, i) => {
      try {
        add(convert(row));
      } catch (err) {
        // Row 1 is the header, so data rows start at 2.
        errors.push(`${file} row ${i + 2}: ${(err as Error).message}`);
      }
    });

  const customers = new Map<string, Customer>();
  each('customers.csv', read('customers.csv'), toCustomer, (c) => customers.set(c.customerId, c));

  const accounts = new Map<string, Account>();
  each('accounts.csv', read('accounts.csv'), (r) => toAccount(r, customers), (a) => accounts.set(a.accountId, a));

  const seen = new Set<string>();
  let duplicatesSkipped = 0;
  const transactions: Transaction[] = [];
  each('transactions.csv', read('transactions.csv'), (r) => toTransaction(r, accounts, rules), (t) => {
    // Idempotent by external transaction ID, like the original import.
    if (seen.has(t.transactionId)) {
      duplicatesSkipped++;
      return;
    }
    seen.add(t.transactionId);
    transactions.push(t);
  });

  return {customers, accounts, transactions, errors, duplicatesSkipped};
}
