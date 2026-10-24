/**
 * PR Sentinel - Google Gemini LLM Provider
 * Interfaces with Google's GenAI SDK (Gemini 2.5 Flash / Pro).
 */

import { GoogleGenAI } from '@google/genai';
import { config } from '../config.js';

let genAIClient = null;

function getClient() {
  if (!genAIClient && config.geminiApiKey) {
    genAIClient = new GoogleGenAI({ apiKey: config.geminiApiKey });
  }
  return genAIClient;
}

/**
 * Generate completion from Gemini model
 * @param {Object} options
 * @param {string} options.systemInstruction System instructions / agent persona
 * @param {string} options.prompt The user prompt or contextual data
 * @param {boolean} [options.jsonMode=false] Whether to request JSON output
 * @param {number} [options.temperature=0.2] Sampling temperature
 * @returns {Promise<{ text: string, data?: any, usage?: any }>}
 */
export async function generateWithGemini({
  systemInstruction,
  prompt,
  jsonMode = false,
  temperature = 0.2,
}) {
  const client = getClient();
  if (!client) {
    throw new Error('GEMINI_API_KEY is not configured or client is unavailable.');
  }

  const modelName = config.geminiModel;

  if (config.quotaExceeded) {
    throw new Error('QUOTA_EXCEEDED: Falling back to Autonomous Simulation Engine.');
  }

  const requestConfig = {
    temperature,
    systemInstruction,
  };

  if (jsonMode) {
    requestConfig.responseMimeType = 'application/json';
  }

  // Wrap API call in a 4.5-second timeout to guarantee responsive UI
  const generatePromise = client.models.generateContent({
    model: modelName,
    contents: prompt,
    config: requestConfig,
  });

  const timeoutPromise = new Promise((_, reject) =>
    setTimeout(() => reject(new Error('TIMEOUT: Gemini API request timed out')), 4500)
  );

  let response;
  try {
    response = await Promise.race([generatePromise, timeoutPromise]);
  } catch (apiErr) {
    if (apiErr.message?.includes('429') || apiErr.message?.includes('RESOURCE_EXHAUSTED') || apiErr.message?.includes('TIMEOUT')) {
      config.quotaExceeded = true;
      console.warn('  ⚠️ Gemini API quota reached or slow response. Falling back to high-fidelity simulation engine.');
    }
    throw apiErr;
  }

  const responseText = response.text || '';
  let parsedData = null;

  if (jsonMode) {
    try {
      // Clean possible markdown code fences if model returned ```json ... ```
      const cleaned = responseText.replace(/^```json\s*/i, '').replace(/```\s*$/, '').trim();
      parsedData = JSON.parse(cleaned);
    } catch (parseError) {
      // Fallback: try to locate the first JSON object or array
      const jsonMatch = responseText.match(/(\{[\s\S]*\}|\[[\s\S]*\])/);
      if (jsonMatch) {
        parsedData = JSON.parse(jsonMatch[0]);
      } else {
        throw new Error(`Failed to parse JSON response from Gemini: ${parseError.message}`);
      }
    }
  }

  return {
    text: responseText,
    data: parsedData,
    usage: response.usageMetadata || null,
  };
}

export default {
  generateWithGemini,
};
