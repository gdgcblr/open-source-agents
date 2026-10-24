import {describe, expect, it} from 'vitest';
import {analyzeMessage} from '../src/analyze.js';
import {evaluate, loadSamples} from '../src/eval.js';
import {redact} from '../src/privacy.js';
import {analyzeUrl, extractUrls, registrableDomain} from '../src/url.js';

const ids = (text: string) => analyzeMessage(text).signals.map((s) => s.id);

describe('text rules', () => {
  it('flags OTP requests but not "never share your OTP" warnings', () => {
    expect(ids('Please share the OTP you received to verify your account.')).toContain('otp_request');
    expect(ids('Never share your OTP with anyone.')).not.toContain('otp_request');
    expect(ids('Do not share this OTP with anyone, including bank staff.')).not.toContain('otp_request');
  });

  it('allows delivery OTPs shared with the delivery partner', () => {
    expect(ids('Share OTP 4821 with the delivery partner only at the time of delivery.')).not.toContain('otp_request');
  });

  it('does not split sentences on "Rs. 500"', () => {
    expect(ids('Earn Rs. 5000 daily by liking videos.')).toContain('task_job');
  });

  it('detects Hindi account-block threats', () => {
    expect(ids('आपका खाता आज बंद हो जाएगा')).toContain('kyc_block');
  });

  it('explains the "PIN to receive money" trick', () => {
    const a = analyzeMessage('I sent a collect request. Enter UPI PIN to receive the money.');
    expect(a.signals.map((s) => s.id)).toContain('pin_to_receive');
    expect(a.advice.join(' ')).toMatch(/never need your UPI PIN/);
  });
});

describe('links', () => {
  it('extracts scheme, www and bare links but not emails or UPI IDs', () => {
    const urls = extractUrls('Visit https://a.example.xyz/x, www.test.in or sbi-help.top. Mail me@gmail.com or pay me@okaxis.');
    expect(urls).toEqual(['https://a.example.xyz/x', 'www.test.in', 'sbi-help.top']);
  });

  it('trusts official domains and their sub-domains', () => {
    expect(analyzeUrl('https://www.amazon.in/progress-tracker')).toMatchObject({official: true, risk: 0});
    expect(analyzeUrl('https://retail.onlinesbi.sbi/login')).toMatchObject({official: true, risk: 0});
  });

  it('catches brand look-alikes and misspellings', () => {
    expect(analyzeUrl('http://sbi-kyc-update.top').reasons[0]).toMatch(/not an official SBI domain/);
    expect(analyzeUrl('https://www.flipkarrt.com/offer').reasons[0]).toMatch(/misspelling of flipkart.com/);
  });

  it('flags shorteners, IPs, punycode and APKs', () => {
    expect(analyzeUrl('bit.ly/abc').risk).toBeGreaterThan(0);
    expect(analyzeUrl('http://192.168.10.5/pay').risk).toBeGreaterThanOrEqual(40);
    // "pаytm.com" with a Cyrillic "а" (U+0430) looks identical to the real domain.
    expect(analyzeUrl('https://p\u0430ytm.com/kyc').reasons.join()).toMatch(/punycode/);
    expect(analyzeUrl('http://update-app.online/bill.apk').reasons.join()).toMatch(/APK/);
  });

  it('handles two-level Indian suffixes', () => {
    expect(registrableDomain('www.incometax.gov.in')).toBe('incometax.gov.in');
    expect(registrableDomain('a.b.example.com')).toBe('example.com');
  });
});

describe('privacy', () => {
  it('masks phones, UPI IDs, emails and account numbers but keeps links', () => {
    const out = redact('Call 98765 43210 or +91-9123456789, pay rahul@okaxis, mail a.b@gmail.com, A/c 123456789012, see http://x.top/9876543210');
    expect(out).toBe('Call [PHONE] or [PHONE], pay [UPI_ID], mail [EMAIL], A/c [NUMBER], see http://x.top/9876543210');
  });
});

describe('labelled samples', () => {
  it('classifies every sample correctly (regression guard)', () => {
    const result = evaluate(loadSamples());
    expect(result.rows.filter((r) => !r.correct).map((r) => r.id)).toEqual([]);
  });
});
