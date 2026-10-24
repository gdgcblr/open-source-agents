import type {Customer} from './types.js';

/** "Krishna Sharma" -> "K****** S*****" (business rule 8: mask PII in list views and for the model). */
export function maskName(customer: Pick<Customer, 'firstName' | 'lastName'>): string {
  return [customer.firstName, customer.lastName].map((p) => (p ? `${p[0]}${'*'.repeat(Math.max(p.length - 1, 1))}` : '')).join(' ').trim();
}

/** Defensive scrub: replaces any of the customer's direct identifiers that appear in free text. */
export function scrubCustomerPii(text: string, customers: Iterable<Customer>): string {
  let out = text;
  for (const c of customers) {
    for (const value of [c.email, c.phone, c.dateOfBirth, `${c.firstName} ${c.lastName}`, c.firstName, c.lastName]) {
      if (value && value.length >= 3) out = out.split(value).join('[REDACTED]');
    }
  }
  return out;
}
