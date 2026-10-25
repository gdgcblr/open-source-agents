import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SERVER_ROOT = path.resolve(HERE, '..');
const ON_OFF = new Set(['on', 'off']);

/** Thrown for invalid configuration. The server refuses to start on bad config. */
export class ConfigError extends Error {
  constructor(message) {
    super(message);
    this.name = 'ConfigError';
  }
}

function pickOnOff(raw, name, fallback) {
  if (raw === undefined || raw === '') return fallback;
  const value = String(raw).trim().toLowerCase();
  if (!ON_OFF.has(value)) throw new ConfigError(`${name} must be "on" or "off"`);
  return value === 'on';
}

function resolveDataDir(raw) {
  const target = raw === undefined || raw === '' ? path.join(SERVER_ROOT, '.data') : raw;
  if (typeof target !== 'string') throw new ConfigError('PINPOINT_DATA_DIR must be a string');
  const resolved = path.resolve(target);
  if (path.parse(resolved).root === resolved) {
    throw new ConfigError('PINPOINT_DATA_DIR must not be a filesystem root');
  }
  try {
    fs.mkdirSync(resolved, { recursive: true });
  } catch (err) {
    throw new ConfigError(`Cannot create data directory "${resolved}": ${err.code ?? err.message}`);
  }
  return resolved;
}

/**
 * Load configuration from an env-like object (defaults to process.env).
 * Creates the data directory if missing; throws ConfigError if that fails.
 */
export function loadConfig(env = process.env) {
  const logLevel = (env.PINPOINT_LOG_LEVEL || 'info').toLowerCase();
  if (!['debug', 'info', 'warn', 'error'].includes(logLevel)) {
    throw new ConfigError('PINPOINT_LOG_LEVEL must be debug, info, warn or error');
  }
  const rateRaw = env.PINPOINT_RATE_LIMIT_PER_MIN;
  const rateLimitPerMin = rateRaw === undefined || rateRaw === '' ? 120 : Number(rateRaw);
  if (!Number.isInteger(rateLimitPerMin) || rateLimitPerMin < 1) {
    throw new ConfigError('PINPOINT_RATE_LIMIT_PER_MIN must be a positive integer');
  }
  return Object.freeze({
    dataDir: resolveDataDir(env.PINPOINT_DATA_DIR),
    logLevel,
    audit: pickOnOff(env.PINPOINT_AUDIT, 'PINPOINT_AUDIT', true),
    redact: pickOnOff(env.PINPOINT_REDACT, 'PINPOINT_REDACT', true),
    rateLimitPerMin,
  });
}
