import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export type Level = 'beginner' | 'intermediate' | 'advanced';
export const LEVELS: Level[] = ['beginner', 'intermediate', 'advanced'];

// Works from both src/ (tsx) and dist/ (compiled): the project root is one level up.
export const PROJECT_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

export interface Config {
  geminiApiKey?: string;
  modelName: string;
  githubToken?: string;
}

export function loadConfig(): Config {
  const envFile = path.join(PROJECT_ROOT, '.env');
  if (existsSync(envFile)) process.loadEnvFile(envFile);
  return {
    geminiApiKey: process.env.GEMINI_API_KEY || undefined,
    modelName: process.env.MODEL_NAME || 'gemini-3.6-flash',
    githubToken: process.env.GITHUB_TOKEN || undefined,
  };
}

export function isValidLevel(level: string): level is Level {
  return (LEVELS as string[]).includes(level);
}

export interface LevelProfile {
  labels: string[];
  repoQualifier: string;
  targetDifficulty: number;
}

const BEGINNER_LABELS = ['good first issue', 'good-first-issue', 'beginner', 'first-timers-only', 'easy'];
const HELP_LABELS = ['help wanted', 'help-wanted'];

export const LEVEL_PROFILES: Record<Level, LevelProfile> = {
  beginner: { labels: BEGINNER_LABELS, repoQualifier: 'good-first-issues:>=2', targetDifficulty: 1.5 },
  intermediate: { labels: [...BEGINNER_LABELS, ...HELP_LABELS], repoQualifier: 'good-first-issues:>=2', targetDifficulty: 3 },
  advanced: { labels: HELP_LABELS, repoQualifier: 'help-wanted-issues:>=2', targetDifficulty: 4.5 },
};

const LANGUAGE_ALIASES: Record<string, string> = {
  js: 'javascript', node: 'javascript', nodejs: 'javascript', ts: 'typescript',
  py: 'python', golang: 'go', cpp: 'c++', csharp: 'c#', rb: 'ruby', sh: 'shell', bash: 'shell',
};

/** Normalise a language name to the value GitHub's `language:` qualifier expects. */
export function normalizeLanguage(input: string): string {
  const lang = input.trim().toLowerCase();
  return LANGUAGE_ALIASES[lang] ?? lang;
}
