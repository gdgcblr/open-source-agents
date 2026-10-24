import * as dotenv from 'dotenv';
dotenv.config();

// Ensure the Google API key exists before any agent initializes
if (!process.env.GOOGLE_GENAI_API_KEY && !process.env.GEMINI_API_KEY) {
  throw new Error('❌ Missing GOOGLE_GENAI_API_KEY in your .env file!');
}

// Centralized model name with fallback
export const MODEL_NAME = process.env.MODEL_NAME || 'gemini-2.5-flash';

// OpenFDA configuration
export const OPENFDA_API_KEY = process.env.OPENFDA_API_KEY || '';