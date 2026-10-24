/**
 * PR Sentinel - Configuration Module
 * Manages environment variables, LLM model settings, and execution modes.
 */

import dotenv from 'dotenv';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Look for .env in project root or current working directory
const possibleEnvPaths = [
  path.resolve(__dirname, '..', '.env'),
  path.resolve(process.cwd(), '.env'),
];

for (const envPath of possibleEnvPaths) {
  if (fs.existsSync(envPath)) {
    dotenv.config({ path: envPath });
    break;
  }
}

export const config = {
  // LLM Provider Settings
  geminiApiKey: process.env.GEMINI_API_KEY || process.env.GOOGLE_API_KEY || '',
  geminiModel: process.env.GEMINI_MODEL || 'gemini-3.8-flash',
  
  // Execution Mode
  mockMode: process.env.MOCK_MODE === 'true' || process.env.DEMO_MODE === 'true',
  
  // Web Dashboard
  port: parseInt(process.env.PORT || '3737', 10),
  host: process.env.HOST || 'localhost',
  
  // Limits and Thresholds
  maxDiffLines: parseInt(process.env.MAX_DIFF_LINES || '5000', 10),
  logLevel: process.env.LOG_LEVEL || 'info',
  
  // Internal state
  quotaExceeded: false,

  // Helper to determine if live Gemini API is configured
  isLiveApiAvailable() {
    return Boolean(this.geminiApiKey && !this.mockMode && !this.quotaExceeded);
  }
};

export default config;
