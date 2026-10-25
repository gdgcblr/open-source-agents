// Gemini adapter (@google/genai). Manual function calling: the agent runs every tool, so the
// allowlist, session injection and confirmation gate always apply. Unit-tested with a fake client
// only. The live path has not been run against the API (see README).

import { GoogleGenAI } from '@google/genai';
import { redactSecret } from '../config.js';

/** Convert the agent's neutral history into Gemini `contents`. */
export function toContents(history) {
  return history.map((entry) => {
    if (entry.role === 'user') return { role: 'user', parts: [{ text: entry.text }] };
    if (entry.role === 'assistant') return { role: 'model', parts: [{ text: entry.text }] };
    if (entry.role === 'model') {
      return { role: 'model', parts: entry.calls.map((c) => ({ functionCall: { id: c.id, name: c.name, args: c.args } })) };
    }
    return {
      role: 'user',
      parts: [{ functionResponse: { id: entry.id, name: entry.name, response: { result: entry.text } } }],
    };
  });
}

/**
 * @param {{ apiKey: string, modelName: string, client?: { models: { generateContent } } }} opts
 *   client is injected in tests; without it a GoogleGenAI client is created from apiKey.
 */
export function createGeminiModel({ apiKey, modelName, client }) {
  const ai = client ?? new GoogleGenAI({ apiKey });
  return {
    name: modelName,
    async next({ systemPrompt, history, tools }) {
      const config = { systemInstruction: systemPrompt };
      if (tools.length > 0) {
        config.tools = [
          {
            functionDeclarations: tools.map((t) => ({
              name: t.name,
              description: t.description,
              parametersJsonSchema: t.inputSchema,
            })),
          },
        ];
      }
      let response;
      let failure = null;
      try {
        response = await ai.models.generateContent({ model: modelName, contents: toContents(history), config });
      } catch (error) {
        // Keep only a redacted message: the original error may carry the key in its text.
        failure = redactSecret(error?.message ?? 'unknown error', apiKey);
      }
      if (failure !== null) throw new Error(`model request failed: ${failure}`);
      const calls = response.functionCalls ?? [];
      if (calls.length > 0) {
        return {
          type: 'tool_calls',
          calls: calls.map((c, index) => ({ id: c.id ?? `call_${index}`, name: c.name, args: c.args ?? {} })),
        };
      }
      return { type: 'text', text: String(response.text ?? '') };
    },
  };
}
