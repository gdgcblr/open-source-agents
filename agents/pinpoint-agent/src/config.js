// Configuration from an env-like object. The Gemini key is read here and nowhere else.
// It is never logged and never passed to the MCP server process.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  DEFAULT_MAX_TOOL_CALLS,
  LOG_LEVELS,
  LOG_LEVEL_DEFAULT,
  MAX_TOOL_CALLS_LIMIT,
  MODEL_NAME_DEFAULT,
  SERVER_RELATIVE_PATH,
} from './constants.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));

export class ConfigError extends Error {
  constructor(message) {
    super(message);
    this.name = 'ConfigError';
  }
}

/** Load .env from the working directory when present (Node 20.12+). */
export function loadDotEnv(file = path.resolve('.env')) {
  if (typeof process.loadEnvFile !== 'function') return;
  let present;
  try {
    present = fs.existsSync(file);
  } catch (error) {
    throw new ConfigError(`cannot check .env: ${error.code ?? error.name}`);
  }
  if (!present) return;
  try {
    process.loadEnvFile(file);
  } catch (error) {
    // Message only: the file content can hold a key, so it is never echoed.
    throw new ConfigError(`cannot load .env: ${error.code ?? error.name}`);
  }
}

export function loadConfig(env = process.env) {
  const apiKey = env.GEMINI_API_KEY?.trim() || null;
  const modelName = env.MODEL_NAME?.trim() || MODEL_NAME_DEFAULT;
  // SERVER_RELATIVE_PATH is relative to the package root, one level above this src/ folder.
  const serverPath = env.PINPOINT_SERVER_PATH
    ? path.resolve(env.PINPOINT_SERVER_PATH)
    : path.resolve(HERE, '..', SERVER_RELATIVE_PATH);
  const dataDir = env.PINPOINT_DATA_DIR?.trim() || null;

  const callsRaw = env.AGENT_MAX_TOOL_CALLS;
  const maxToolCalls = callsRaw === undefined || callsRaw === '' ? DEFAULT_MAX_TOOL_CALLS : Number(callsRaw);
  if (!Number.isInteger(maxToolCalls) || maxToolCalls < 1 || maxToolCalls > MAX_TOOL_CALLS_LIMIT) {
    throw new ConfigError(`AGENT_MAX_TOOL_CALLS must be an integer 1-${MAX_TOOL_CALLS_LIMIT}`);
  }
  const logLevel = (env.AGENT_LOG_LEVEL || LOG_LEVEL_DEFAULT).toLowerCase();
  if (!LOG_LEVELS.includes(logLevel)) throw new ConfigError('AGENT_LOG_LEVEL must be debug, info, warn or error');

  return Object.freeze({ apiKey, modelName, serverPath, dataDir, maxToolCalls, logLevel });
}

/** Replace the secret wherever it appears. Used on any text that might carry it. */
export function redactSecret(text, secret) {
  const value = String(text);
  if (!secret) return value;
  return value.split(secret).join('[REDACTED:api-key]');
}
