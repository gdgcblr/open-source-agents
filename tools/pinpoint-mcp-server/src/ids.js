import crypto from 'node:crypto';

const ALPHABET = '0123456789abcdefghijklmnopqrstuvwxyz';
const SUFFIX_LENGTH = 6;

/** Prefixes: s_ (session), m_ (message), p_ (pin). Format: `<prefix>_<time36>_<6 random>`. */
export function newId(prefix, now = Date.now()) {
  let suffix = '';
  for (let i = 0; i < SUFFIX_LENGTH; i++) {
    suffix += ALPHABET[crypto.randomInt(ALPHABET.length)];
  }
  return `${prefix}_${now.toString(36)}_${suffix}`;
}
