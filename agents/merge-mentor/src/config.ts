import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { DEFAULT_MODEL, LANGUAGE_ALIASES, LEVELS } from './constants.js';
import type { Config, Level } from './types.js';

// Works from both src/ (tsx) and dist/ (compiled): the project root is one level up.
export const PROJECT_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
/** The recorded data behind demo mode. */
export const FIXTURE_FILE = path.join(PROJECT_ROOT, 'fixtures', 'demo.json');

export function loadConfig(): Config {
  const envFile = path.join(PROJECT_ROOT, '.env');
  if (existsSync(envFile)) process.loadEnvFile(envFile);
  return {
    geminiApiKey: process.env.GEMINI_API_KEY || undefined,
    modelName: process.env.MODEL_NAME || DEFAULT_MODEL,
    githubToken: process.env.GITHUB_TOKEN || undefined,
  };
}

export function isValidLevel(level: string): level is Level {
  return (LEVELS as string[]).includes(level);
}

/** Normalise a language name to the value GitHub's `language:` qualifier expects. */
export function normalizeLanguage(input: string): string {
  const lang = input.trim().toLowerCase();
  return LANGUAGE_ALIASES[lang] ?? lang;
}
