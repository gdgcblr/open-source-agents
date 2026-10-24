import type { JsonValue } from './types.js';

const SENSITIVE_KEY =
  /password|secret|token|authorization|cookie|credential|api.?key|private.?key|thought|reasoning|signature/i;
const MAX_NODES = 128;
const MAX_DEPTH = 5;
const MAX_STRING = 1024;
const USAGE_COUNTERS = new Set([
  'inputTokens',
  'outputTokens',
  'totalTokens',
  'reasoningTokens',
  'cachedTokens',
]);

/** Args: text to filter. Returns: bounded redacted text. Raises: none. */
export function redactText(text: string): string {
  const result = text
    .slice(0, MAX_STRING)
    .replace(/Bearer\s+[\w.\-+/=]+/gi, 'Bearer [REDACTED]')
    .replace(/\b(?:sk-[\w-]{8,}|AIza[\w-]{20,}|gh[pousr]_[\w]{16,})\b/g, '[REDACTED]')
    .replace(/\beyJ[\w-]+\.[\w-]+\.[\w-]+\b/g, '[REDACTED]')
    .replace(/-----BEGIN [\w ]*PRIVATE KEY-----[\s\S]*/g, '[REDACTED]')
    .replace(
      /((?:api[_-]?key|password|secret|token)\s*[=:]\s*)[^\s,;]+/gi,
      '$1[REDACTED]',
    );
  return text.length > MAX_STRING ? `${result}…[TRUNCATED]` : result;
}

/** Args: arbitrary data. Returns: bounded JSON without getters or raw errors. Raises: none. */
export function sanitize(value: unknown): JsonValue {
  const seen = new WeakSet<object>();
  let remaining = MAX_NODES;
  function visit(item: unknown, depth: number): JsonValue {
    if (--remaining < 0 || depth > MAX_DEPTH) return '[TRUNCATED]';
    if (item === null || typeof item === 'boolean') return item;
    if (typeof item === 'string') return redactText(item);
    if (typeof item === 'number') return Number.isFinite(item) ? item : null;
    if (typeof item !== 'object') return '[UNSUPPORTED]';
    if (seen.has(item)) return '[CIRCULAR]';
    if (item instanceof Error || ArrayBuffer.isView(item)) return '[OMITTED]';
    seen.add(item);
    const result = visitObject(item, depth, visit);
    seen.delete(item);
    return result;
  }
  try {
    return visit(value, 0);
  } catch {
    return '[UNREADABLE]';
  }
}

function visitObject(
  value: object,
  depth: number,
  visit: (value: unknown, depth: number) => JsonValue,
): JsonValue {
  if (Array.isArray(value)) {
    const length = Object.getOwnPropertyDescriptor(value, 'length')?.value as number;
    return Array.from({ length: Math.min(length, 32) }, (_, index) => {
      const descriptor = Object.getOwnPropertyDescriptor(value, String(index));
      return descriptor ? visitProperty('', descriptor, depth, visit) : null;
    });
  }
  const result: Record<string, JsonValue> = Object.create(null) as Record<
    string,
    JsonValue
  >;
  let examined = 0;
  for (const key in value) {
    if (++examined > 32) break;
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (
      !descriptor?.enumerable ||
      ['__proto__', 'prototype', 'constructor'].includes(key)
    )
      continue;
    result[redactText(key)] = visitProperty(key, descriptor, depth, visit);
  }
  return result;
}

function visitProperty(
  key: string,
  descriptor: PropertyDescriptor,
  depth: number,
  visit: (value: unknown, depth: number) => JsonValue,
): JsonValue {
  const isCounter =
    USAGE_COUNTERS.has(key) &&
    Number.isSafeInteger(descriptor.value) &&
    (descriptor.value as number) >= 0;
  if (SENSITIVE_KEY.test(key) && !isCounter) return '[REDACTED]';
  return 'value' in descriptor ? visit(descriptor.value, depth + 1) : '[ACCESSOR]';
}

/** Args: label to validate. Returns: bounded display name. Raises: TypeError on invalid label. */
export function validateName(value: string): string {
  if (
    typeof value !== 'string' ||
    !value.trim() ||
    value.length > 128 ||
    /[\x00-\x1f\x7f]/.test(value)
  ) {
    throw new TypeError('Names must contain 1–128 printable characters.');
  }
  return redactText(value);
}

/** Args: optional integer and limits. Returns: validated value. Raises: RangeError if invalid. */
export function boundedInteger(
  value: number | undefined,
  fallback: number,
  min: number,
  max: number,
): number {
  const selected = value ?? fallback;
  if (!Number.isSafeInteger(selected) || selected < min || selected > max) {
    throw new RangeError(`Expected an integer between ${min} and ${max}.`);
  }
  return selected;
}
